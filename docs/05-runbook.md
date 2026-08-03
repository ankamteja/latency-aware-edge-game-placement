# 5. Runbook

From a cold machine to raw data on disk.

---

## 5.0 Prerequisites

| Need | Check | If missing |
|---|---|---|
| Docker, and your user in the `docker` group | `docker ps` works without sudo | `sudo usermod -aG docker $USER`, then log out and back in |
| containerlab | `containerlab version` | https://containerlab.dev/install/ |
| Permission to run containerlab without root | `containerlab inspect --all` works | add your user to the `clab_admins` group |
| Node modules for the bots | `ls bots/node_modules/mineflayer` | `cd bots && npm ci` |
| A prepared server data source | `docker volume ls` shows the volume named in `topology/prepare.sh` | see §5.6 |
| Free cores | `nproc` >= 24 | shrink the `cpu-set` ranges in the topology file |

The testbed pins containers to host cores 0-1, 2-7 and 8-23. On a machine with
fewer cores, edit the `cpu-set` values in `topology/edge-cloud.clab.yml` first,
keeping the three ranges disjoint.

---

## 5.1 Bring the testbed up

```bash
cd topology
./prepare.sh          # first time only: builds nodes/edge and nodes/cloud (~510 MB)
./up.sh               # build client image, deploy, wait, apply netem, verify
```

`up.sh` takes the two RTT targets as arguments; `./up.sh 5 40` is the default.

Expected tail of the output:

```
== measured RTT (this is the number that goes in the write-up)
  ok   edge (10.0.1.2) min/avg/max/mdev = 5.051/5.113/5.186/0.038 ms, 0% packet loss
  ok   cloud (10.0.2.2) min/avg/max/mdev = 40.081/40.144/40.331/0.059 ms, 0% packet loss
== game servers
  ok   edge accepting connections | There are 0 of a max of 100 players online:
  ok   cloud accepting connections | There are 0 of a max of 100 players online:

ALL CHECKS PASSED
```

The edge node takes about 60-90 s to become ready because it is loading the
world on half a core. The cloud node takes a few seconds.

**If anything says FAIL, stop.** Go to
[06-troubleshooting.md](06-troubleshooting.md). Do not collect data against a
testbed that did not verify - every check in `verify.sh` guards a failure mode
that produces plausible-looking but worthless numbers.

---

## 5.2 Smoke test before the full grid

The full grid is ~40 minutes unattended, and this rig has historically failed
in ways that leave you with a directory full of empty files. Always run one
short cell first:

```bash
cd ../controller
./collect.sh --targets edge --loads 5 --duration 60 --idle 20 --tag smoke
```

Then confirm all four streams landed non-empty:

```bash
cd ../results/raw/smoke/edge-5bots
wc -l bot.csv probe.csv icmp.txt server.csv
grep -c ',rtt,'    bot.csv      # should be roughly (bots x steady seconds)
grep -c ',status,' probe.csv    # should be roughly (total seconds)
grep -c 'time='    icmp.txt     # same
grep -c ',kicked'  bot.csv      # must be 0
cat meta.json                   # players_held must equal bots
```

**The sample count is the regression test for the respawn bug**, so make it
exact. Each bot sends one chat message per second, and the bots only exist from
the moment they join, so the whole file should hold

```
about  N x duration           samples inside the steady window
plus   up to N x join_wait     from the staggered join (join_wait = N/2 + 10)
```

For `edge-40bots` with the defaults that is ~4800 in the steady window and
~5200 in the file - and the run measured 4779 and 5236. **Several times that
means bots are sending faster than intended**, which is the bug in
[06-troubleshooting.md §6.2](06-troubleshooting.md). Restrict the count to the
steady window using the timestamps in `meta.json` if you want the tight number:

```bash
python3 - <<'PY'
import json
m = json.load(open('meta.json'))
n = sum(1 for l in open('bot.csv')
        if ',rtt,' in l and m['steady_start_ms'] <= int(l.split(',')[0]) <= m['steady_end_ms'])
print(n, 'expected about', m['bots'] * m['duration_seconds'])
PY
```

Delete the smoke run when satisfied:

```bash
rm -rf results/raw/smoke topology/out/smoke
```

---

## 5.3 Run the full collection

```bash
cd controller
nohup ./collect.sh --tag run1 > collect-run1.log 2>&1 &
```

`nohup ... &` detaches it so it survives the terminal closing. Watch it with:

```bash
tail -f collect-run1.log
```

Per-cell output looks like:

```
=== edge-20bots  (target 10.0.1.2)
    settling 30s
    idle baseline 20s
    steady load 120s (20 players attached)
    held 20 players, 0 kicks, 2410 rtt samples
```

The three things to watch on every line: **players attached equals the bot
count**, **kicks is 0**, and **rtt samples is in the expected range**.

Options:

| Option | Default | Notes |
|---|---|---|
| `--targets` | `edge,cloud` | comma list |
| `--loads` | `1,5,10,20,30,40` | capped at 40 by the opped usernames in the server data |
| `--duration` | `120` | seconds of steady load per cell |
| `--idle` | `20` | seconds of probe-only baseline |
| `--settle` | `30` | seconds of recovery between cells |
| `--tag` | UTC timestamp | output directory name |

Total wall time is roughly
`cells x (settle + idle + join + duration + ~10 s)`. The default grid is about
40 minutes.

---

## 5.4 After the run

Raw streams land in `results/raw/<tag>/`. Check each cell held its load:

```bash
cd results/raw/run1
for d in */; do
  printf '%-16s bots=%s held=%s kicks=%s rtt=%s\n' "$d" \
    "$(grep -o '"bots": [0-9]*'         "$d/meta.json" | grep -o '[0-9]*')" \
    "$(grep -o '"players_held": [0-9-]*' "$d/meta.json" | grep -o '[0-9-]*')" \
    "$(grep -c ',kicked' "$d/bot.csv")" \
    "$(grep -c ',rtt,'   "$d/bot.csv")"
done
```

Any cell where `held` does not equal `bots`, or `kicks` is not 0, is suspect
and should be re-run rather than analysed.

---

## 5.5 Shut down

```bash
cd topology
./down.sh              # remove the containers and links
./down.sh --clean      # also delete the ~510 MB of per-node server data
```

Leaving the lab up between sessions is fine; the servers idle at a few percent
CPU. Leaving it up *during* other heavy work on the same machine is not - the
core pinning protects against CPU contention from the measurement rig itself,
not from unrelated workloads.

---

## 5.6 If the prepared server volume is gone

`prepare.sh` copies from a Docker named volume left over from the earlier
single-node experiments. If it no longer exists, build an equivalent from
scratch once:

```bash
docker run -d --name mcseed -p 25565:25565 \
  -e EULA=TRUE -e TYPE=PAPER -e VERSION=1.21.4 -e ONLINE_MODE=FALSE \
  itzg/minecraft-server

# wait for it to finish generating the world
docker exec mcseed mc-monitor status --host 127.0.0.1

# settings the experiment needs
docker exec mcseed sh -c "sed -i 's/^max-players=.*/max-players=100/' /data/server.properties"
docker exec mcseed sh -c "sed -i 's/connection-throttle:.*/connection-throttle: -1/' /data/bukkit.yml"
docker restart mcseed
for i in $(seq 0 39); do docker exec mcseed rcon-cli op bot$i; done
```

Then find the volume it created and pass its name to `prepare.sh`:

```bash
docker inspect mcseed --format '{{ (index .Mounts 0).Name }}'
./prepare.sh <that-name>
```

Opping `bot0`..`bot39` requires each name to be known to the server, so if
`op` reports the player is unknown, join once with `node bots/bot.js 40` before
opping.

Why each setting:

| Setting | Without it |
|---|---|
| `max-players=100` | the default 20 caps the grid at 20 bots |
| `connection-throttle: -1` | the default 4000 ms rejects bots joining 500 ms apart |
| `online-mode=false` | bots have no Mojang accounts and cannot log in |
| bots opped | the vanilla anti-spam filter kicks anything chatting once a second, and it fires *sooner* when the server is already behind - i.e. exactly during the runs you care about |
