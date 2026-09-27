/*
 * workspace_guard.ts — confine pi's file tools to the workspace.
 *
 * pi has no permission system and runs with the user's permissions. The tool
 * allowlist removes shell execution; this extension is the second layer, and it
 * is what confines the tools that remain.
 *
 * It hooks `tool_call`, which fires before a tool executes and can veto the
 * call. Any path argument that resolves outside the workspace is blocked.
 *
 * Known limits, stated plainly (see docs/security/threat-model.md):
 *   - Network access is NOT contained.
 *   - Prompt injection from a file inside the workspace is NOT contained.
 *   - This runs in-process with pi's permissions, so it constrains policy,
 *     not a hostile pi build.
 *
 * Loaded with: pi --no-extensions -e <this file>
 */

import * as fs from "node:fs";
import * as path from "node:path";

/** Tools whose call arguments carry a filesystem path. */
const PATH_ARGS: Record<string, string[]> = {
    read: ["path"],
    write: ["path"],
    edit: ["path"],
    ls: ["path"],
    find: ["path", "cwd"],
    grep: ["path", "cwd"],
};

/** A working directory the guard should not restrict (pi's own agent dir). */
const ALLOWED_PREFIXES = ["~/.pi", "~/.config/pi"];

function expandHome(p: string): string {
    if (p === "~") return process.env.HOME ?? p;
    if (p.startsWith("~/")) {
        return path.join(process.env.HOME ?? "~", p.slice(2));
    }
    return p;
}

/** Resolve symlinks, tolerating a path that does not exist yet (a new file). */
function realpathOrSelf(p: string): string {
    try {
        return fs.realpathSync(p);
    } catch {
        try {
            return path.join(fs.realpathSync(path.dirname(p)), path.basename(p));
        } catch {
            return p;
        }
    }
}

function isInsideWorkspace(target: string, workspace: string): boolean {
    // Resolve symlinks so a link inside the workspace cannot point outside it.
    const resolved = realpathOrSelf(path.resolve(workspace, expandHome(target)));
    const root = realpathOrSelf(path.resolve(workspace));

    // A shared separator boundary, so /work-evil does not pass as inside /work.
    if (resolved === root) return true;
    return resolved.startsWith(root + path.sep);
}

export default function workspaceGuard(pi: any): void {
    const workspace = process.cwd();

    pi.on("tool_call", (event: any) => {
        const tool = event?.toolName ?? event?.name ?? "";
        const argNames = PATH_ARGS[tool];
        if (!argNames) return;

        const input = event?.input ?? event?.args ?? {};
        for (const argName of argNames) {
            const value = input[argName];
            if (typeof value !== "string" || value.length === 0) continue;

            const expanded = expandHome(value);
            // pi's own agent dir is not restricted; continue so a multi-argument
            // tool (find/grep carry both path and cwd) still checks its other args.
            const inAgentDir = ALLOWED_PREFIXES.some(
                (p) => path.resolve(expandHome(p)) === path.resolve(expanded)
            );
            if (inAgentDir) continue;

            if (!isInsideWorkspace(value, workspace)) {
                return {
                    block: true,
                    reason:
                        `workspace_guard: ${tool} path ${JSON.stringify(value)} ` +
                        `is outside the workspace (${workspace})`,
                };
            }
        }
        return;
    });

    // Best-effort: surface the guard's presence in pi's start-up log.
    try {
        pi.log?.(`workspace_guard active, workspace=${workspace}`);
    } catch {
        // logging is optional
    }
}

/** Exported for unit testing the path check without a pi process. */
export function _isInsideWorkspaceForTest(target: string, workspace: string): boolean {
    return isInsideWorkspace(target, workspace);
}

// Keep the import used so bundlers do not drop fs; pi injects the directory API.
void fs;
