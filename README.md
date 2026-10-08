# Hallevault

A personal file vault with a quiet green interface. Upload and download work files, organize them in folders, and replace files when you have a newer copy. Files are stored on the server, so you can access them from different devices.

**First login:** username `Anna`, password `byxficka`. Change the password under **Settings** as soon as you sign in.

## Run on your computer

Install Python 3.9 or newer, open a terminal in this folder, and run:

```sh
DATA_DIR=./data REQUIRE_STORAGE=false python3 server.py
```

Open **http://127.0.0.1:8080** in your browser. Leave the terminal running; press Ctrl+C to stop the app. This local demo command explicitly uses `./data` without requiring the mounted drive. Running `python3 server.py` with no overrides checks `/var/www/hallevault` and shows the warning if it is unavailable. No Python packages or JavaScript build tools are required.

The app creates a `data` directory on first launch. It contains the database, account, and uploaded files. Keep it when updating the application. Starting the app again preserves your files and changed password.

## Using your vault

- **Upload files:** choose one or more files, or drop them onto the file list. The default limit is 200 MB per file.
- **New folder:** create a folder in the current location. Click its name to open it, and use the breadcrumb path to go back.
- **Download:** click a file name or choose Download in its three-dot menu.
- **Replace file:** choose this in a file's menu and select the new file. The existing name and folder are kept. The old contents are permanently replaced; this app does not keep previous versions.
- **Rename / Move:** use an item's menu. Moving a folder also moves everything inside it.
- **Delete:** requires confirmation. Folders must be empty first. There is no recycle bin.
- **Search:** filters the current folder by name.
- **Settings:** enter your current password and a new password of at least 10 characters. Other signed-in sessions are invalidated. Sessions expire after 24 hours.

## Deploy alongside your existing services

`compose2.yaml` includes `version: '3'` for your older `docker-compose` command. If using that command, replace `docker compose` with `sudo docker-compose` in the examples. Keep the version line when copying the file to `docker-compose.yaml`.

`compose2.yaml` contains your count-down, file-sharer, virtual-piano, and Nginx reverse services, plus Hallevault on port **8093**. It uses your existing reverse proxy; Caddy is not included in this configuration.

Place `compose2.yaml` next to your existing `docker-compose.yaml`, and copy this application's source into a `hallevault/` directory alongside `count-down/`, `apache2-container/`, `virtualPiano/`, and `nginx/`. The new service builds from `./hallevault/Dockerfile`. If you give that directory a different name, update the build context.

Prepare `/media/pi/Seagate/hallevault` and its marker using the storage setup instructions below. Then, from the directory containing `compose2.yaml`, start the new service:

```sh
docker compose -f compose2.yaml up -d --build hallevault
```

Open `http://YOUR_PI_IP:8093`. Anna's initial password is `byxficka`. If storage is not prepared, the warning banner will appear instead of allowing login. Keep using `-f compose2.yaml` for commands targeting this configuration. To manage the entire stack, run `docker compose -f compose2.yaml up -d --build`.

The storage path remains `/media/pi/Seagate/hallevault` on the host and `/var/www/hallevault` inside the container. This configuration sets `SECURE_COOKIES=false` to allow login over your existing HTTP setup. For HTTPS, set it to `true` after configuring TLS on your reverse proxy.

The supplied `nginx/conf.d/sites-available/hallevault.conf` matches your existing Nginx layout. It uses **hallevault.ricardicus.se** as the proposed hostname; change its `server_name` if you prefer another hostname. Point its DNS record to the same public IP as `hem.ricardicus.se`.

From `~/dev/rpi-server`, copy the supplied configuration from the Hallevault project into your existing Nginx directory, then enable it:

```sh
cp hallevault/nginx/conf.d/sites-available/hallevault.conf nginx/conf.d/sites-available/hallevault.conf
ln -s ../sites-available/hallevault.conf nginx/conf.d/sites-enabled/hallevault.conf
docker compose -f compose2.yaml up -d --build hallevault
docker compose -f compose2.yaml up -d --build reverse
docker compose -f compose2.yaml exec reverse nginx -t
```

If `sites-enabled/hallevault.conf` already exists, skip the `ln -s` command. This assumes your existing Nginx image copies `conf.d/` and `nginx.conf` includes `sites-enabled/`, as your other sites require. If your enabled configurations are regular copies instead of symlinks, use `cp nginx/conf.d/sites-available/hallevault.conf nginx/conf.d/sites-enabled/hallevault.conf` instead. Inspect the reverse service logs if it does not start.

Open **http://hallevault.ricardicus.se** after DNS resolves. This configuration uses HTTP, matching the existing reverse proxy. Serve the app at the root of its hostname; its URLs do not support a `/hallevault/` subpath. For backup/reset commands below, use `docker compose -f compose2.yaml` and replace the service name `vault` with `hallevault`.

## Deploy on a server

This setup uses a Linux server with Docker Compose, a domain name, and Caddy for HTTPS. It runs one Hallevault instance with persistent Docker storage. Static hosting such as GitHub Pages cannot run this app.

### 1. Prepare your server and domain

Get a Linux server with enough disk space for your files. Install Docker Engine and the Compose plugin using the [official installation guide](https://docs.docker.com/engine/install/). Confirm both work:

```sh
docker --version
docker compose version
```

At your domain provider, add an **A record** for a name such as `files.example.com`, pointing to your server's public IPv4 address. If you also add an AAAA record, it must point to a working IPv6 address on the same server.

Allow incoming TCP ports **80 and 443** through both your provider's firewall and the server's firewall. UDP 443 is optional for HTTP/3. Keep SSH access available. The application port 8080 is internal and does not need to be opened publicly.

Caddy obtains and renews HTTPS certificates automatically when the domain points to your server and the required ports are reachable. See [Caddy's HTTPS setup](https://caddyserver.com/docs/quick-starts/https).

### 2. Copy and configure the application

Copy this project to your server, for example into `/opt/hallevault`. You need `server.py`, `public/`, `Dockerfile`, `compose.yaml`, and `Caddyfile`. Do not copy your local `data/` directory unless intentionally migrating it.

In that directory:

```sh
cp .env.example .env
```

Edit `.env` and replace the example with your real domain:

```dotenv
VAULT_DOMAIN=files.example.com
```

Use only the hostname, without `https://` or a trailing slash.

### 3. Start Hallevault

Make sure the Seagate drive is mounted at `/media/pi/Seagate`. Create the storage directory and give the container user (UID/GID 10001) permission to write to it:

```sh
mountpoint /media/pi/Seagate
sudo mkdir -p /media/pi/Seagate/hallevault
sudo touch /media/pi/Seagate/hallevault/.hallevault-storage
sudo chown -R 10001:10001 /media/pi/Seagate/hallevault
```

Confirm the drive is mounted **before creating the directory or marker**. Continue only if `mountpoint` confirms the drive is mounted. On filesystems without Unix ownership support, configure the drive's mount options to allow UID/GID 10001 to write instead of using `chown`.

From the project directory, run:

```sh
docker compose up -d --build
```

Then open **https://files.example.com** (using your actual hostname). Sign in as Anna with `byxficka`, go to Settings, and change the password. Upload a test file and download it to confirm the deployment works.

The containers restart automatically after server restarts. Caddy handles HTTPS and redirects HTTP to HTTPS. Secure cookies are enabled in the supplied production configuration; use the HTTPS URL to sign in.

### 4. Check or troubleshoot it

```sh
docker compose ps
docker compose logs --tail=100 vault caddy
```

If the page is unreachable, check DNS and ports 80/443. If Caddy cannot obtain a certificate, its logs explain the failure; also check for incorrect AAAA records and another service occupying those ports. If you cannot sign in, verify you are using HTTPS, and remember that the initial password is only used when the database is first created.

## Lost storage message

Compose enables `REQUIRE_STORAGE=true`. The `.hallevault-storage` marker created during setup identifies the prepared storage directory. If it disappears, or the directory, database, or file storage directory is missing, the GUI displays: **“Lost contact with the mounted harddrive- ask Rickard to fix it.”** File operations and login are blocked; the app does not silently create a new empty vault. The warning is a banner at the top of the page, visible even before sign-in and included in the initial HTML so JavaScript is not needed to display it. The GUI checks every ten seconds and offers **Try again**.

For an existing deployment, stop the app, confirm the drive is mounted, and create the marker using the setup commands above before updating. On a fresh installation the marker allows the database and default account to be initialized. After recovering a drive, restart the container if necessary. An empty file list in an intact vault is normal and does not trigger this message. This marker checks storage presence; it cannot detect every hardware fault or prove the host drive is still physically mounted.

## Where your files live

The host directory `/media/pi/Seagate/hallevault` is mounted at `/var/www/hallevault` inside the application container. It contains `vault.sqlite` and `files/`. The database stores names, folder relationships, password hashes, and sessions. Uploaded contents use random storage names; downloading restores the original filename. The application does not execute or render uploaded files.

The vault data stays on the Seagate drive across container rebuilds. Caddy uses separate named volumes for its certificates and configuration.

Keep the Seagate drive mounted whenever Hallevault is running. Deleting the host storage directory deletes your vault. `docker compose down -v` removes Caddy’s named volumes but does not remove this bind-mounted directory. If migrating from the earlier `vault-data` named volume, stop the app and copy its full contents into the host directory before starting with this configuration; changing the mount does not migrate existing files automatically.

## Backups and recovery

Back up regularly and keep a copy on another machine. The backup includes the database and file contents together. Stop the application briefly so they remain consistent. Run from the project directory:

```sh
mkdir -p backups
docker compose stop vault
docker compose run --rm --no-deps -T vault python -c 'import tarfile; t=tarfile.open(fileobj=__import__("sys").stdout.buffer, mode="w|gz"); t.add("/var/www/hallevault", arcname="."); t.close()' > backups/vault-backup.tar.gz
docker compose start vault
```

Check that the backup command succeeded before relying on the archive. This filename is reused: rename the archive with a date after each backup. The archive contains your files and account database, so protect it like the vault itself. Also keep a copy of this source directory and `.env` so you can recreate the deployment.

To restore on a fresh deployment with an empty `/media/pi/Seagate/hallevault` directory (prepared with the permissions above), place the backup in `backups/`, configure `.env`, and run:

```sh
docker compose build vault
docker compose run --rm --no-deps -T vault python -c 'import tarfile; t=tarfile.open(fileobj=__import__("sys").stdin.buffer, mode="r|gz"); t.extractall("/var/www/hallevault"); t.close()' < backups/vault-backup.tar.gz
docker compose up -d
```

Only restore a backup you created and trust. Restore into an empty storage directory; to replace an existing deployment, first back it up and stop it, then have your server administrator clear only `/media/pi/Seagate/hallevault`. The restored password is the password at backup time. Test a download after restoring. Caddy can obtain new certificates on a fresh server.

For local Python use, stop the app and copy the entire `data/` directory. Restore that directory before restarting.

## Updates

Make a backup first, copy updated source files into the same deployment directory, and run:

```sh
docker compose up -d --build
```

Your Seagate storage directory remains in place. This implementation has no external Python or JavaScript dependencies. Container base images still need periodic updates:

```sh
docker compose pull caddy
docker compose build --pull vault
docker compose up -d
```

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `HOST` | `127.0.0.1` | Listening interface. Docker sets `0.0.0.0`. |
| `PORT` | `8080` | Application port. |
| `DATA_DIR` | `/var/www/hallevault` | Database and uploaded file directory. Compose uses `/var/www/hallevault`. |
| `MAX_FILE_MB` | `200` | Maximum file size in MiB. |
| `REQUIRE_STORAGE` | `true` | Require the prepared storage marker; Compose sets `true`. |
| `SECURE_COOKIES` | `false` | Set `true` behind HTTPS; Compose already does. |
| `INITIAL_PASSWORD` | `byxficka` | Used only when creating the first account. |

If increasing the upload limit, increase `max_size` in `Caddyfile` too. Total storage is limited by the server disk; monitor available space. Files are not encrypted at rest by this app; use encrypted server storage if needed. Backups are necessary to recover from disk loss or accidental deletion.

This is a single-account, single-server app for personal use. It has no public registration, sharing links, file version history, or desktop synchronization. The HTTP server handles requests sequentially without spawning worker threads, and closes each connection after its response. This avoids request-thread failures on constrained hosts. Requests are serialized to keep database and file operations consistent; large transfers can delay other requests. The login limit is ten failed attempts per source IP in five minutes and resets on process restart. With Caddy in front, clients share the proxy IP for this limit.

## Raspberry Pi: 502 with “can’t start new thread”

This error means the previous threaded server could not start a request worker. The updated server handles requests without creating threads. Copy the updated `server.py` to your Pi’s `hallevault/` directory, then rebuild and recreate only that service:

```sh
sudo docker compose build hallevault
sudo docker compose up -d --no-deps --force-recreate hallevault
curl -i --max-time 10 http://127.0.0.1:8093/api/storage
```

The data directory is preserved. The `version is obsolete` warning from modern Compose does not cause the 502. This change avoids the app’s thread requirement; it does not diagnose why the host refuses thread creation.

## Forgotten password

A server administrator can reset Anna's password. Stop the app first. For Docker, run this interactive command (the new password is entered privately):

```sh
docker compose stop vault
docker compose run --rm --no-deps vault python -c 'import server, getpass; p=getpass.getpass("New password (at least 10 characters): "); assert 10 <= len(p) <= 1024, "Password length must be 10–1024"; c=server.db(); c.execute("UPDATE users SET password=? WHERE username=?", (server.password_hash(p), "Anna")); c.execute("DELETE FROM sessions"); c.commit(); c.close()'
docker compose start vault
```

This keeps all files and signs out every session. Changing `INITIAL_PASSWORD` does not reset an existing account.

## Verification

```sh
python3 -m unittest discover -s tests -v
node --check public/app.js
```

The automated test exercises the HTTP request handler and real temporary database/file storage: authentication, CSRF protection, folders, upload, download, replacement, size limits, invalid names, moving, deletion, password changes, and logout. Node is only needed for the optional JavaScript syntax check.
