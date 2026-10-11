# SPDX-License-Identifier: GPL-2.0-or-later
PREFIX     ?= /usr/local
SBINDIR    ?= $(PREFIX)/sbin
SYSCONFDIR ?= /etc
UNITDIR    ?= $(SYSCONFDIR)/systemd/system
COMPLETIONDIR ?= $(PREFIX)/share/bash-completion/completions
SPOOLDIR   ?= /var/spool/blocklists
# owner of the spool directory, must match User=/Group= of the units
SPOOL_USER ?= wwwrun
SPOOL_GROUP ?= www

UNITS = update-blocklist@.service update-blocklist@.timer \
        update-blocklist.service update-blocklist.timer

.PHONY: all check install install-files install-spool uninstall

all: check

check:
	python3 -m unittest discover -s tests

install: install-files install-spool
	@test -n "$(DESTDIR)" || echo "Now run: systemctl daemon-reload"

# everything but the spool directory, which needs root to set its owner
install-files:
	install -D -m 755 blocklist $(DESTDIR)$(SBINDIR)/blocklist
	install -d $(DESTDIR)$(UNITDIR)
	for u in $(UNITS); do \
		sed -e 's|/usr/local/sbin/|$(SBINDIR)/|' \
		    -e 's|^User=.*|User=$(SPOOL_USER)|' -e 's|^Group=.*|Group=$(SPOOL_GROUP)|' \
		    systemd/$$u > $(DESTDIR)$(UNITDIR)/$$u && \
		chmod 644 $(DESTDIR)$(UNITDIR)/$$u || exit 1; \
	done
	install -D -m 644 systemd/update-blocklist@abuseipdb.service.d/credential.conf \
		$(DESTDIR)$(UNITDIR)/update-blocklist@abuseipdb.service.d/credential.conf
	install -D -m 644 systemd/update-blocklist@abuseipdb.timer.d/schedule.conf \
		$(DESTDIR)$(UNITDIR)/update-blocklist@abuseipdb.timer.d/schedule.conf
	# never overwrite an existing configuration
	test -e $(DESTDIR)$(SYSCONFDIR)/blocklists/blocklists.conf || \
		install -D -m 644 blocklists.conf $(DESTDIR)$(SYSCONFDIR)/blocklists/blocklists.conf
	install -D -m 644 completions/blocklist $(DESTDIR)$(COMPLETIONDIR)/blocklist

install-spool:
	install -d -m 755 -o $(SPOOL_USER) -g $(SPOOL_GROUP) $(DESTDIR)$(SPOOLDIR)

uninstall:
	rm -f $(DESTDIR)$(SBINDIR)/blocklist $(DESTDIR)$(COMPLETIONDIR)/blocklist
	for u in $(UNITS); do rm -f $(DESTDIR)$(UNITDIR)/$$u; done
	rm -rf $(DESTDIR)$(UNITDIR)/update-blocklist@abuseipdb.service.d \
		$(DESTDIR)$(UNITDIR)/update-blocklist@abuseipdb.timer.d
	@echo "Kept $(SYSCONFDIR)/blocklists and $(SPOOLDIR)"
