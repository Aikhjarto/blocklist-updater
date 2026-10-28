# blocklist-updater

Downloads IP blocklists from several providers, validates and merges them into
one list, and publishes it, e.g. on a Nextcloud share. Other machines fetch the
list from there and block the addresses with
[block-badips](https://github.com/Aikhjarto/block-badips) (version 0.6.0 or
later, which blocks ranges via `hash:net` ipsets).

```
update-blocklist@<source>.timer ─► blocklist fetch <source> ─► /var/spool/blocklists/<source>.txt
                                                                          │
update-blocklist.timer (hourly, :50) ─► blocklist assemble ◄──────────────┘
                                         └─► output file ─► post_publish (occ files:scan)
```

## Features

- One script for all providers. Each provider is a section in
  `/etc/blocklists/blocklists.conf` and is switched on by enabling its timer.
- Parsers for plain lists, Spamhaus DROP JSON and DShield `block.txt`.
- A failed or broken download (HTML error page, too few entries, many invalid
  entries) keeps the previous list of that provider.
- Before publishing, entries are dropped that are
  - broader than `min_prefix_v4` / `min_prefix_v6`,
  - private, reserved or documentation networks,
  - covered by another entry.

  Entries overlapping a `never_block` network (your own addresses) are split
  around it.
- Lists of providers that stopped updating drop out after `max_age_days`.
- A list that shrank by more than `max_shrink_percent` is not published unless
  `blocklist assemble --force` is used.
- All files are replaced atomically, so consumers never read a half-written
  list. `post_publish` runs only when the content changed.
- API keys are passed with systemd's `LoadCredential=`, not stored in the
  units or the configuration.
- Hardened systemd units (`ProtectSystem=strict`, minimal write access, no
  capabilities).

## Providers

Configured in the sample `blocklists.conf`, all free of charge:

| Section | List | Notes |
|---|---|---|
| `spamhaus-drop`, `spamhaus-drop-v6` | [Spamhaus DROP](https://www.spamhaus.org/blocklists/do-not-route-or-peer/) | hijacked netblocks; EDROP was merged into DROP in 2024 |
| `gpf` | [GPF DNS Block List](https://www.gpf-comics.com/dnsbl/) | |
| `abuseipdb` | [AbuseIPDB blacklist](https://docs.abuseipdb.com/#blacklist-endpoint) | needs a free API key, 5 downloads per day |
| `blocklist-de` | [blocklist.de](https://www.blocklist.de/en/export.html) | attacks reported by fail2ban users within 48 h |
| `cinsscore` | [CINS Army](https://cinsscore.com/#list) | |
| `et-compromised` | [Emerging Threats](https://rules.emergingthreats.net/blockrules/) | compromised hosts |
| `greensnow` | [GreenSnow](https://greensnow.co/) | |
| `dshield` | [DShield](https://feeds.dshield.org/) | top 20 /24 networks, CC BY-NC-SA |

Check each provider's terms of use before redistributing its data.

## Installation

Requirements: Python 3.9 or later (standard library only), systemd.

```sh
make check                     # run the tests
make install                   # SPOOL_USER/SPOOL_GROUP default to wwwrun/www
systemctl daemon-reload
```

`make install` puts the script into `/usr/local/sbin`, the units into
`/etc/systemd/system`, the bash completion into
`/usr/local/share/bash-completion/completions`, and the sample configuration
into `/etc/blocklists/blocklists.conf`, unless that file already exists. The
units get the script's path and `User=`/`Group=` from `SBINDIR` and
`SPOOL_USER`/`SPOOL_GROUP`, e.g. on Debian:

```sh
make install PREFIX=/usr SPOOL_USER=www-data SPOOL_GROUP=www-data
```

`make install-files` installs everything but the spool directory and works
without root, e.g. with `DESTDIR` for packaging.

Packages for openSUSE, Debian and Ubuntu are built on the
[openSUSE Build Service](https://build.opensuse.org/package/show/home:Aikhjarto/blocklist-updater).
They install the script into `/usr/sbin` and the units into
`/usr/lib/systemd/system`, create `/var/spool/blocklists` with
systemd-tmpfiles, run the units as the web server user (`wwwrun`/`www` on
openSUSE, `www-data` on Debian and Ubuntu), and enable nothing.

Then:

1. Edit `/etc/blocklists/blocklists.conf`: `output`, `post_publish` and
   `never_block` (your own addresses).
2. Allow the assemble service to write the output, e.g. with
   `examples/nextcloud.conf` as
   `/etc/systemd/system/update-blocklist.service.d/nextcloud.conf`.
   `User=`/`Group=` in the units must be the web server user if `occ` is used.
3. For AbuseIPDB, store the API key root-only:
   ```sh
   install -m 600 /dev/null /etc/blocklists/abuseipdb.key
   echo 'YOUR-KEY' > /etc/blocklists/abuseipdb.key
   ```
4. Enable the providers and the fallback assembly:
   ```sh
   systemctl enable --now update-blocklist@spamhaus-drop.timer update-blocklist@blocklist-de.timer
   systemctl enable --now update-blocklist.timer
   ```

## Operation

```sh
systemctl start update-blocklist@blocklist-de.service    # download one provider now
systemctl start update-blocklist.service                 # assemble now
sudo -u wwwrun blocklist assemble --force                # publish despite the shrink guard
systemctl disable --now update-blocklist@gpf.timer       # stop using a provider
journalctl -t blocklist-assemble -t blocklist-blocklist-de
```

A disabled provider drops out once its list is older than `max_age_days`. To
drop it at once, delete `/var/spool/blocklists/<source>.txt` and assemble.

The published list has one IPv4/IPv6 address or CIDR range per line and no
comments. Single addresses are written without `/32` or `/128`.

## Bash completion

`completions/blocklist` completes the commands, `--force`, and for `fetch`
the sources of the configuration file (`BLOCKLIST_CONFIG` or
`/etc/blocklists/blocklists.conf`, if readable). `make install` and the
packages install it.

## Adding a provider

Add a section to `blocklists.conf`:

```ini
[example]
url = https://example.org/list.txt
format = plain          # plain, spamhaus-json or dshield
max_age_days = 2        # optional
min_entries = 10        # optional
```

then `systemctl enable --now update-blocklist@example.timer`. For a new list
format, add a parser function to `PARSERS` in `blocklist` and a test.

## License

GPL-2.0-or-later, see [COPYING](COPYING).
