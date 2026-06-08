// Tests for telemetry-log.js — self-instrumentation for user-typed slash
// commands that don't fire PostToolUse:Skill (the documented coverage gap in
// command-usage-logger.cjs). Verifies logCommand writes a well-formed
// command_invocation row to command-usage.jsonl under the resolved project root.

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { createRequire } from 'node:module';
import fs from 'node:fs';
import path from 'node:path';

const require = createRequire(import.meta.url);
const { logCommand } = require('../telemetry-log');
const { createTmpDir } = require('./_helpers/tmp-dir');

let tmp;
beforeEach(() => { tmp = createTmpDir({ prefix: 'telemetry-log-test-' }); });
afterEach(() => { tmp.cleanup(); });

function readRows(root) {
    const p = path.join(root, 'docs', '.output', 'telemetry', 'command-usage.jsonl');
    return fs.readFileSync(p, 'utf8').trim().split('\n').map(l => JSON.parse(l));
}

describe('telemetry-log.logCommand', () => {
    it('writesCommandInvocationRow_withSelfInstrumentedSource', () => {
        logCommand('onboard', null, tmp.root);

        const rows = readRows(tmp.root);
        expect(rows).toHaveLength(1);
        expect(rows[0].type).toBe('command_invocation');
        expect(rows[0].command).toBe('onboard');
        expect(rows[0].source).toBe('self-instrumented');
        expect(rows[0].duration_ms).toBeNull();
        expect(typeof rows[0].timestamp).toBe('string');
    });

    it('coercesNumericDuration_andLeavesNaNAsNull', () => {
        logCommand('run-todo', 8500, tmp.root);
        logCommand('do', Number('nope'), tmp.root);

        const rows = readRows(tmp.root);
        expect(rows[0].duration_ms).toBe(8500);
        expect(rows[1].duration_ms).toBeNull();
    });

    it('appendsRatherThanOverwrites', () => {
        logCommand('onboard', null, tmp.root);
        logCommand('prime', null, tmp.root);

        const rows = readRows(tmp.root);
        expect(rows.map(r => r.command)).toEqual(['onboard', 'prime']);
    });
});
