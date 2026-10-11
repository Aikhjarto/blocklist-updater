# SPDX-License-Identifier: GPL-2.0-or-later
PREFIX     ?= /usr/local
SBINDIR    ?= $(PREFIX)/sbin
SYSCONFDIR ?= /etc
UNITDIR    ?= $(SYSCONFDIR)/systemd/system
SPOOLDIR   ?= /var/spool/blocklists
# owner of the spool directory, must match User=/Group= of the units
SPOOL_USER ?= wwwrun
SPOOL_GROUP ?= www

UNITS = update-blocklist@.service update-blocklist@.timer \
        update-blocklist.service update-blocklist.timer

.PHONY: all check install uninstall

all: check

check:
	python3 -m unittest discover -s tests

install:
	install -D -m 755 blocklist $(DESTDIR)$(SBINDIR)/blocklist
	for u in $(UNITS); do install -D -m 644 systemd/$$u $(DESTDIR)$(UNITDIR)/$$u; done
	install -D -m 644 systemd/update-blocklist@abuseipdb.service.d/credential.conf \
		$(DESTDIR)$(UNITDIR)/update-blocklist@abuseipdb.service.d/credential.conf
	install -D -m 644 systemd/update-blocklist@abuseipdb.timer.d/schedule.conf \
		$(DESTDIR)$(UNITDIR)/update-blocklist@abuseipdb.timer.d/schedule.conf
	# never overwrite an existing configuration
	test -e $(DESTDIR)$(SYSCONFDIR)/blocklists/blocklists.conf || \
		install -D -m 644 blocklists.conf $(DESTDIR)$(SYSCONFDIR)/blocklists/blocklists.conf
	install -d -m 755 -o $(SPOOL_USER) -g $(SPOOL_GROUP) $(DESTDIR)$(SPOOLDIR)
	@test -n "$(DESTDIR)" || echo "Now run: systemctl daemon-reload"

uninstall:
	rm -f $(DESTDIR)$(SBINDIR)/blocklist
	for u in $(UNITS); do rm -f $(DESTDIR)$(UNITDIR)/$$u; done
	rm -rf $(DESTDIR)$(UNITDIR)/update-blocklist@abuseipdb.service.d \
		$(DESTDIR)$(UNITDIR)/update-blocklist@abuseipdb.timer.d
	@echo "Kept $(SYSCONFDIR)/blocklists and $(SPOOLDIR)"
