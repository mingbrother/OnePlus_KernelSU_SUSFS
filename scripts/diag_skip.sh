#!/usr/bin/env bash
# Diagnostic patch-gating helpers.
#
# The build pipeline applies a handful of patches / forced kconfig options that
# upstream (WildKernels) applies unconditionally but the OnePlus stock kernel
# does not. When bisecting a stock-vs-custom regression there has to be a way to
# build the same tree without them, otherwise those deltas can never be
# excluded.
#
# OP_SKIP_PATCHES is exported into the job environment by the action's
# "Parse op_config_json" step (space-separated token list, empty by default).
# Recognised tokens:
#   ptrace          - skip gki_ptrace.patch (5.15 ptrace_message refactor)
#   module_overlay  - skip the module intercept/overlay patch (and its module copy)
#   fake_config     - skip common/fake_config.patch (embedded /proc/config.gz)
#   netsch          - do not force CONFIG_NET_SCH_CAKE / _PIE / _FQ_PIE =y
#   tmpfs           - do not force CONFIG_TMPFS_XATTR / _POSIX_ACL =y
#
# Usage from a step:
#   source "$GITHUB_WORKSPACE/scripts/diag_skip.sh"
#   if skip_patch ptrace; then echo "skipping"; fi

OP_SKIP_PATCHES="${OP_SKIP_PATCHES:-}"

skip_patch() {
	local token="$1"
	case " ${OP_SKIP_PATCHES} " in
		*" ${token} "*) return 0 ;;
		*) return 1 ;;
	esac
}

# Echo the whole skip list, for build summaries / logs.
skip_patch_list() {
	printf '%s\n' "${OP_SKIP_PATCHES:-<none>}"
}
