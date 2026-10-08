// Runs a Python script with the repo's virtual environment when there is one, else `python` on PATH.
import { existsSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { resolve } from "node:path";

const repo = resolve(import.meta.dirname, "../../..");
const candidates = [resolve(repo, ".venv/Scripts/python.exe"), resolve(repo, ".venv/bin/python")];
const python = candidates.find(existsSync) ?? "python";
const run = spawnSync(python, ["-X", "utf8", ...process.argv.slice(2)], { stdio: "inherit" });
process.exit(run.status ?? 1);
