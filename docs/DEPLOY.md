# v1 deployment on the Oracle VM - step-by-step guide

> Goal: leave Oscilion running 24/7 in dry-run, generating signals (ntfy) and **minimal
> logs** that can be reviewed daily. It never trades with money. Repo:
> `https://github.com/oscardanielnc/oscilion-b26.git`

> Note: the VM service was stopped on 2026-08-03 when the project was closed (see
> `docs/AUDIT_2026-08-03.md`). This guide documents how it was deployed.

## 0. Before (on your PC)
Push the committed code to GitHub:
```bash
git push -u origin main
```

## 1. Initial provisioning on the VM (once)
SSH into the VM and, as root/sudo:
```bash
# download the provisioning script and run it (clone, venv, deps, seed data, systemd)
curl -fsSL https://raw.githubusercontent.com/oscardanielnc/oscilion-b26/main/setup_vm.sh -o /tmp/setup_vm.sh
sudo bash /tmp/setup_vm.sh
```
This:
1. creates the `oscilion` service user and `/opt/oscilion`,
2. installs python/venv/git, clones the repo, creates the venv and installs dependencies,
3. creates `/etc/oscilion.env` from `example.env` (`dry-run` mode) and **sets
   `OSCILION_FORWARD_INCEPTION_MS` to the deployment date** (from then on = unseen data =
   real forward). Edit it afterwards to set `OSCILION_NTFY_TOPIC=<your-private-topic>`,
4. **seeds 3 years of history** for the core coins (the ones defined in
   `assignment.py`) - takes ~5-10 min,
5. installs and starts the systemd services (`oscilion` = monitor, `oscilion-api` = API).

> If data seeding fails because of the network, re-run:
> `sudo -u oscilion /opt/oscilion/.venv/bin/python -m oscilion.data sync --days 1095`

## 2. Check that it runs
```bash
systemctl status oscilion oscilion-api          # both "active (running)"
journalctl -u oscilion -n 30 --no-pager         # startup + heartbeat (minimal logs)
sudo -u oscilion /opt/oscilion/.venv/bin/python -m oscilion.live.forward   # validation table
```

## 3. Mobile alerts (ntfy)
Install the **ntfy** app (iOS/Android) -> subscribe to the topic **`<your-private-topic>`**.
You receive ENTER / EXIT / TAKE_PROFIT in real time. (Test:
`curl -d "test" ntfy.sh/<your-private-topic>`.) The topic name works as a password: use a
long random string.

## 4. View the dashboard (safely, without exposing ports)
The API listens on `127.0.0.1:8787` (not exposed to the internet). From your PC, open an
SSH tunnel:
```bash
ssh -L 8787:127.0.0.1:8787 user@VM_IP
# then open in your browser:  http://localhost:8787
```

## 5. Future updates (ONE command)
After pushing changes from your PC, on the VM from **any** directory:
```bash
bash /opt/oscilion/deploy.sh
```
It does everything: `git pull` -> dependencies -> import check -> **backfill of new
coins** -> restarts `oscilion` and `oscilion-api` -> status summary. It does not need
`sudo` (it uses it internally only for systemctl). If the import fails, it **aborts without
restarting**.

> **Automatic, idempotent backfill:** when new coins are added to the core
> (`assignment.py`), the deploy seeds them by itself (`python -m oscilion.data backfill`):
> it downloads full history ONLY for those below 1500 1h candles and skips the ones already
> seeded (fast deploy). It keeps a new coin from starting "dark" (build_ctx needs >= 300 1h
> candles). Force it manually: `... -m oscilion.data backfill`.
>
> **Frontend:** the dashboard is served from the **committed** `frontend/dist` (the VM does
> not build). If you change `frontend/src`, rebuild and commit `dist` BEFORE deploying:
> `cd frontend && npm run build` (on your PC) -> `git add frontend/dist && git commit`.

## 6. Daily review (MINIMAL logs to share)
Any of these is concise enough to share for a review:
```bash
# A) validation: backtest vs forward per coin x strategy (the most useful one)
sudo -u oscilion /opt/oscilion/.venv/bin/python -m oscilion.live.forward

# B) recent alerts (the day's signals)
curl -s 127.0.0.1:8787/alerts | python3 -m json.tool | head -40

# C) recent service events/errors
journalctl -u oscilion --since "24 hours ago" -p info --no-pager | tail -40
```
The log design is **append-only and minimal**: only alerts, decisions, errors and an
hourly heartbeat are recorded. The noisy detail (fetch, ticks) goes to DEBUG (not stored).

## Notes
- **Dry-run** mode: it records and alerts, it **never places orders**. For `paper`/`live`
  (never built) `OSCILION_MODE` would change and credentials would be added, but first the
  forward test had to confirm the edge.
- Virtual positions and cursors **survive restarts** (persisted in the DB) -> the forward
  test does not lose continuity when the service restarts.
- `forward_inception` is fixed at deployment: the forward accumulates from that day on;
  review it after days/weeks.
