PREFIX ?= $(HOME)/.local
SRC := $(abspath symphony.py)

# Symlink, not copy: edits here take effect at once. Moving this folder breaks the link; rerun `make install`.
install:
	chmod +x $(SRC)
	mkdir -p $(PREFIX)/bin
	ln -sf $(SRC) $(PREFIX)/bin/symphony
	@echo "installed $(PREFIX)/bin/symphony -> $(SRC)"

uninstall:
	rm -f $(PREFIX)/bin/symphony

# The skill install logic lives in the CLI: `symphony install [--agent claude|agents] [--dir SKILLS_DIR]`.
install-skill:
	python3 $(SRC) install

uninstall-skill:
	python3 $(SRC) uninstall

test:
	python3 -m unittest discover -s .

.PHONY: install uninstall install-skill uninstall-skill test
