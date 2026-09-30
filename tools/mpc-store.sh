#!/bin/sh
# mpc-store: install, update, remove and list catalog plugins on an MPC OS device. BusyBox sh + wget/curl + unzip + sha256sum.
# Run on the device as root:
#   sh mpc-store.sh [-y] [-t <synths-dir>] [--url <catalog.tsv url>] [--dry-run] <command> [args]
#     list                       the catalog's plugins, what is installed ("manual" = a folder that was not put there by this script), what is newer
#     install <id[@version]>...  download, verify (sha256 from the catalog), then stop MPC once, run each zip's own install.sh, start MPC
#     update [id...]             install the newest version of what is installed (a major version change needs --major)
#     remove <id>...             delete the plugin folder (your own files in it are kept) and its plugin-list entry
#     sync                       register plugin folders that have no entry and drop entries whose file is gone (sync.sh)
# Nothing on the device changes until every download has been verified and you confirmed (-y skips the question). MPC is stopped
# once and started once, and is started again if something fails. What was installed is remembered in <synths-dir>/.mpc-store.
# The catalog is https://sd88me.github.io/mpc-vst-plugins/catalog.tsv (docs/CATALOG.md); the helper files it lists (sync.sh,
# plugin_list.awk) are fetched from the same folder and checked against the hashes in it. Build-yourself plugins are not here.
set -e
URL="${MPC_STORE_URL:-https://sd88me.github.io/mpc-vst-plugins/catalog.tsv}"
SYNTHS=/sdcard/Synths; YES=0; DRY=0; MAJOR=0
TAB=$(printf '\t')
die() { echo "error: $*" >&2; exit 1; }
while [ $# -gt 0 ]; do
    case "$1" in
        -y) YES=1; shift ;;
        --dry-run) DRY=1; shift ;;
        --major) MAJOR=1; shift ;;
        -t) [ -n "$2" ] || die "-t needs a folder"; SYNTHS="$2"; shift 2 ;;
        --url) [ -n "$2" ] || die "--url needs a link"; URL="$2"; shift 2 ;;
        -*) die "unknown option $1 (see the top of this file)" ;;
        *) break ;;
    esac
done
CMD="${1:-}"; [ -n "$CMD" ] || die "usage: sh mpc-store.sh [-y] [-t <synths-dir>] [--url <url>] [--dry-run] list|install|update|remove|sync [ids]"
shift
case "$SYNTHS" in /*) ;; *) die "-t must be an absolute path" ;; esac
case "$SYNTHS" in *"&"*|*"|"*|*"\\"*) die "the Synths path may not contain & | or backslash" ;; esac
if [ -z "$MPC_INSTALL_TEST" ] && [ "$CMD" != list ] && [ $DRY = 0 ]; then
    [ "$(id -u)" = 0 ] || die "run as root"
    case "$(uname -m)" in armv7*) ;; *) die "this is for 32-bit ARM MPC OS devices (Gen1); this one is $(uname -m)" ;; esac
    command -v systemctl >/dev/null || die "systemctl not found"
fi
SETTINGS="${MPC_SETTINGS:-$(ls /media/az01-internal/Settings/*/MPC.settings 2>/dev/null | head -n 1)}"
W="${MPC_STORE_TMP:-/tmp}/mpc-store.$$"; mkdir -p "$W" || die "cannot create $W"
trap 'rm -rf "$W"' EXIT
STATE="$SYNTHS/.mpc-store"

fetch() {   # fetch <url> <dest>
    if command -v wget >/dev/null 2>&1; then wget -q -O "$2" "$1" || return 1
    elif command -v curl >/dev/null 2>&1; then curl -fsSL -o "$2" "$1" || return 1
    else die "neither wget nor curl found"; fi
}
sha_of() { sha256sum "$1" | cut -d' ' -f1; }

echo "Reading the catalog: $URL"
fetch "$URL" "$W/catalog.tsv" || die "cannot download the catalog (is the device online?)"
head -n 1 "$W/catalog.tsv" | grep -q '^#mpc-catalog-tsv 1' || die "that is not a catalog this script understands"
BASE="${URL%/*}"

row() {   # row <id> [version]: the catalog line (latest when no version)
    awk -F'\t' -v id="$1" -v v="${2:-}" '$1 == "plugin" && $2 == id && ((v == "" && $4 == 1) || (v != "" && $3 == v)) { print; exit }' "$W/catalog.tsv"
}
col() { echo "$1" | cut -d"$TAB" -f"$2"; }   # plugin id version latest kind name skin uid param_compat size sha256 url user_data
installed_version() { [ -f "$STATE" ] && awk -F'\t' -v id="$1" '$1 == id { print $2; exit }' "$STATE"; }
installed_compat() { [ -f "$STATE" ] && awk -F'\t' -v id="$1" '$1 == id { print $4; exit }' "$STATE"; }
record() {   # record <id> <version> <skin> <param_compat>
    mkdir -p "$SYNTHS"; touch "$STATE"
    awk -F'\t' -v id="$1" '$1 != id' "$STATE" > "$STATE.new" || true
    printf '%s\t%s\t%s\t%s\n' "$1" "$2" "$3" "$4" >> "$STATE.new"; mv "$STATE.new" "$STATE"
}
forget() { [ -f "$STATE" ] || return 0; awk -F'\t' -v id="$1" '$1 != id' "$STATE" > "$STATE.new" || true; mv "$STATE.new" "$STATE"; }
helper() {   # helper <file>: download a helper listed in the catalog and check its hash
    [ -f "$W/h/$1" ] && return 0
    mkdir -p "$W/h"
    want=$(awk -F'\t' -v f="$1" '$1 == "#file" && $2 == f { print $3; exit }' "$W/catalog.tsv")
    [ -n "$want" ] || die "the catalog does not list $1"
    fetch "$BASE/$1" "$W/h/$1" || die "cannot download $1"
    [ "$(sha_of "$W/h/$1")" = "$want" ] || die "$1 does not match the hash in the catalog: not using it"
}
mpc_ctl() {   # stop | start; a test run logs the call to $MPC_TEST_LOG instead of touching MPC
    if [ -n "$MPC_INSTALL_TEST" ]; then [ -z "$MPC_TEST_LOG" ] || echo "$1" >> "$MPC_TEST_LOG"; return 0; fi
    systemctl "$1" acvs
}
stop_mpc() {
    mpc_ctl stop
    trap 'mpc_ctl start; rm -rf "$W"' EXIT
    if [ -z "$MPC_INSTALL_TEST" ]; then
        i=0; while pidof MPC >/dev/null && [ $i -lt 30 ]; do sleep 1; i=$((i + 1)); done
        pidof MPC >/dev/null && die "MPC did not stop"
    fi
}
confirm() {   # confirm <question>
    [ $YES = 1 ] && return 0
    printf "%s [y/N] " "$1"; read -r ok; case "$ok" in y|Y|yes) return 0 ;; *) echo "cancelled"; exit 1 ;; esac
}

do_list() {
    printf '%-18s %-9s %-10s %s\n' "ID" "LATEST" "INSTALLED" "NAME"
    awk -F'\t' '$1 == "plugin" && $4 == 1 { print $2 "\t" $3 "\t" $6 "\t" $7 }' "$W/catalog.tsv" | while IFS=$TAB read -r id ver name skin; do
        inst=$(installed_version "$id" || true)
        if [ -z "$inst" ]; then if [ -d "$SYNTHS/$skin" ]; then inst="manual"; else inst="-"; fi; fi
        mark=""; if [ "$inst" != "-" ] && [ "$inst" != "manual" ] && [ "$inst" != "$ver" ]; then mark="  (update available)"; fi
        printf '%-18s %-9s %-10s %s%s\n' "$id" "$ver" "$inst" "$name" "$mark"
    done
}

# install_rows <catalog line>...: download and verify everything first, then one stop/start around all the installs
do_install_rows() {
    n=0; : > "$W/todo"
    for r in "$@"; do
        id=$(col "$r" 2); ver=$(col "$r" 3); size=$(col "$r" 10); sha=$(col "$r" 11); url=$(col "$r" 12)
        echo "Downloading $id $ver ($((size / 1024)) KB)"
        fetch "$url" "$W/$id.zip" || die "cannot download $url"
        [ "$(sha_of "$W/$id.zip")" = "$sha" ] || die "$id $ver does not match its sha256 in the catalog: nothing was installed"
        mkdir -p "$W/x/$id"; unzip -q -o "$W/$id.zip" -d "$W/x/$id" || die "cannot unpack $id"
        rm -f "$W/$id.zip"
        dir=$(ls -d "$W/x/$id"/*/ 2>/dev/null | head -n 1); dir="${dir%/}"
        [ -f "$dir/install.sh" ] || die "$id $ver has no install.sh"
        printf '%s\n' "$r" >> "$W/todo"; n=$((n + 1))
    done
    [ $n -gt 0 ] || { echo "Nothing to install."; return 0; }
    echo "Verified. About to install:"; awk -F'\t' '{ print "  " $2 " " $3 " (" $6 ")" }' "$W/todo"
    [ $DRY = 1 ] && { echo "Dry run: nothing changed."; return 0; }
    confirm "MPC will be stopped once and restarted at the end. Save your project first. Continue?"
    stop_mpc
    ok=0
    while IFS=$TAB read -r kind id ver latest k name skin uid compat size sha url ud; do
        dir=$(ls -d "$W/x/$id"/*/ | head -n 1); dir="${dir%/}"
        echo "Installing $name $ver"
        if sh "$dir/install.sh" -y -n -t "$SYNTHS"; then record "$id" "$ver" "$skin" "$compat"; ok=$((ok + 1))
        else echo "error: $name failed; continuing would leave a mixed state, so stopping here" >&2; break; fi
    done < "$W/todo"
    echo "Installed $ok of $n. MPC is being started."
    [ $ok = $n ] || return 1
}

do_install() {
    [ $# -gt 0 ] || die "install what? (see: list)"
    : > "$W/rows"
    for a in "$@"; do
        id="${a%%@*}"; ver=""; case "$a" in *@*) ver="${a#*@}" ;; esac
        r=$(row "$id" "$ver"); [ -n "$r" ] || die "$a is not in the catalog as a downloadable plugin (build-yourself plugins are built from your own files: see their README)"
        printf '%s\n' "$r" >> "$W/rows"
    done
    set --; while IFS= read -r line; do set -- "$@" "$line"; done < "$W/rows"
    do_install_rows "$@"
}

do_update() {
    [ -f "$STATE" ] || { echo "Nothing installed through mpc-store yet."; return 0; }
    ids="$*"; [ -n "$ids" ] || ids=$(cut -f1 "$STATE")
    set --
    for id in $ids; do
        cur=$(installed_version "$id" || true); [ -n "$cur" ] || { echo "$id: not installed through mpc-store, skipped"; continue; }
        r=$(row "$id" ""); [ -n "$r" ] || { echo "$id: not in the catalog any more, skipped"; continue; }
        ver=$(col "$r" 3); [ "$ver" != "$cur" ] || { echo "$id: up to date ($cur)"; continue; }
        oc=$(installed_compat "$id" || true); nc=$(col "$r" 9)
        if [ -n "$oc" ] && [ "$oc" != "$nc" ] && [ $MAJOR = 0 ]; then
            echo "$id: $ver is a major change (saved projects using it will change): not updated. Run with --major to allow it."; continue
        fi
        echo "$id: $cur -> $ver"; set -- "$@" "$r"
    done
    [ $# -gt 0 ] || { echo "Everything is up to date."; return 0; }
    do_install_rows "$@"
}

do_remove() {
    [ $# -gt 0 ] || die "remove what?"
    helper plugin_list.awk
    for id in "$@"; do
        r=$(row "$id" ""); [ -n "$r" ] || die "$id is not in the catalog"
        skin=$(col "$r" 7); [ -d "$SYNTHS/$skin" ] || die "$id is not installed in $SYNTHS"
        echo "Will remove $SYNTHS/$skin (keeping: $(col "$r" 13))"
    done
    [ $DRY = 1 ] && { echo "Dry run: nothing changed."; return 0; }
    confirm "MPC will be stopped once and restarted at the end. Save your project first. Continue?"
    [ -n "$SETTINGS" ] && [ -f "$SETTINGS" ] || die "MPC.settings not found"
    stop_mpc
    BAK="$SETTINGS.bak-store-$(date +%Y%m%d-%H%M%S)"; cp "$SETTINGS" "$BAK"
    cp "$SETTINGS" "$W/cur"
    for id in "$@"; do
        r=$(row "$id" ""); skin=$(col "$r" 7); uid=$(col "$r" 8); keep=$(col "$r" 13)
        awk -v mode=remove -v file="$SYNTHS/$skin/.none" -v uid="$uid" -f "$W/h/plugin_list.awk" "$W/cur" > "$W/next" && mv "$W/next" "$W/cur"
        if [ -n "$keep" ] && [ "$keep" != "-" ]; then   # keep the user's own folders: move them out, delete the rest, move them back
            mkdir -p "$W/keep/$id"; oldifs=$IFS; IFS=,
            for d in $keep; do
                if [ -e "$SYNTHS/$skin/$d" ]; then mkdir -p "$W/keep/$id/$(dirname "$d")"; mv "$SYNTHS/$skin/$d" "$W/keep/$id/$d"; fi
            done
            IFS=$oldifs
            rm -rf "$SYNTHS/$skin"
            if [ -n "$(ls -A "$W/keep/$id" 2>/dev/null)" ]; then
                mkdir -p "$SYNTHS/$skin"; cp -a "$W/keep/$id/." "$SYNTHS/$skin/"; echo "kept your files in $SYNTHS/$skin"
            fi
        else rm -rf "$SYNTHS/$skin"; fi
        forget "$id"; echo "removed $id"
    done
    grep -q '<PROPERTIES' "$W/cur" && grep -q '</PROPERTIES>' "$W/cur" || die "edited settings lost their root element; MPC.settings unchanged"
    if command -v python3 >/dev/null; then
        python3 -c 'import sys, xml.etree.ElementTree as E; E.parse(sys.argv[1])' "$W/cur" 2>/dev/null || die "edited settings aren't valid XML; MPC.settings unchanged"
    fi
    cp "$W/cur" "$SETTINGS.new" && mv "$SETTINGS.new" "$SETTINGS"; sync
    echo "Done. Settings backup: $BAK. MPC is being started."
}

do_sync() {
    helper sync.sh; helper plugin_list.awk
    args=""; [ $YES = 1 ] && args="-y"; [ $DRY = 1 ] && args="$args --dry-run"
    # shellcheck disable=SC2086
    sh "$W/h/sync.sh" $args -t "$SYNTHS"
}

case "$CMD" in
    list) do_list ;;
    install) do_install "$@" ;;
    update) do_update "$@" ;;
    remove) do_remove "$@" ;;
    sync) do_sync ;;
    *) die "unknown command $CMD (list, install, update, remove, sync)" ;;
esac
