// Tests for feedback-digest.js — the automated telemetry rollup behind
// /review:feedback. Each reader takes an explicit root, so we build a synthetic
// project tree in a tmp dir and assert the digest reflects it.

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { createRequire } from 'node:module';
import fs from 'node:fs';
import path from 'node:path';

const require = createRequire(import.meta.url);
const {
    buildDigest,
    renderMarkdown,
    summarize,
    readCommandUsage,
    readMemoryStore,
    readSystemFiles,
} = require('../feedback-digest');
const { createTmpDir } = require('./_helpers/tmp-dir');

let tmp;
beforeEach(() => { tmp = createTmpDir({ prefix: 'feedback-digest-' }); });
afterEach(() => { tmp.cleanup(); });

const TEL = 'docs/.output/telemetry';

function writeJsonl(relPath, rows) {
    tmp.write(relPath, rows.map(r => JSON.stringify(r)).join('\n') + '\n');
}

describe('readCommandUsage', () => {
    it('countsInvocations_selfInstrumented_andGateOutcomes', () => {
        writeJsonl(`${TEL}/command-usage.jsonl`, [
            { type: 'command_invocation', command: 'onboard', source: 'self-instrumented' },
            { type: 'command_invocation', command: 'review:specialize' },
            { type: 'gate_run', command: 'gate:test', outcome: 'success', duration_ms: 4000 },
            { type: 'gate_run', command: 'gate:build', outcome: 'failure', duration_ms: 2000 },
            { type: 'gate_run', command: 'gate:test', outcome: 'unknown' },
        ]);
        const r = readCommandUsage(tmp.root);
        expect(r.totalInvocations).toBe(2);
        expect(r.selfInstrumented).toBe(1);
        expect(r.invocations.onboard).toBe(1);
        expect(r.gates.runs).toBe(3);
        expect(r.gates.pass).toBe(1);
        expect(r.gates.fail).toBe(1);
        expect(r.gates.unknown).toBe(1);
        expect(r.gates.passRate).toBe(50); // 1 pass / 2 decided
        expect(r.gates.avgDurationMs).toBe(3000); // (4000+2000)/2
    });

    it('missingFile_degradesToZeros', () => {
        const r = readCommandUsage(tmp.root);
        expect(r.totalInvocations).toBe(0);
        expect(r.gates.runs).toBe(0);
        expect(r.gates.passRate).toBeNull();
    });
});

describe('readMemoryStore', () => {
    it('countsJsonByCategory_excludesDailyAndInbox', () => {
        tmp.write('docs/.output/memories/patterns/a.json', '{}');
        tmp.write('docs/.output/memories/patterns/b.json', '{}');
        tmp.write('docs/.output/memories/decisions/adr-001.json', '{}');
        tmp.write('docs/.output/memories/daily/2026-06-06.md', '# log'); // excluded
        tmp.write('docs/.output/memories/_inbox/draft.json', '{}'); // excluded
        const r = readMemoryStore(tmp.root);
        expect(r.total).toBe(3);
        expect(r.byCategory).toEqual({ patterns: 2, decisions: 1 });
    });
});

describe('readSystemFiles', () => {
    it('countsAgentsSkillsCommandsHooks_andVersion', () => {
        tmp.write('.claude/agents/architect.md', '# a');
        tmp.write('.claude/agents/doc-writer.md', '# b');
        tmp.write('.claude/skills/code-review/SKILL.md', '# s');
        tmp.write('.claude/skills/code-review/references/x.md', 'ignored'); // not SKILL.md
        tmp.write('.claude/commands/onboard.md', '# c');
        tmp.write('.claude/commands/review/feedback.md', '# c2');
        tmp.write('.claude/hooks/guardrail.cjs', '//h');
        tmp.write('.claude/version.json', JSON.stringify({ version: '4.46.0' }));
        const r = readSystemFiles(tmp.root);
        expect(r.agents).toBe(2);
        expect(r.skills).toBe(1);
        expect(r.commands).toBe(2);
        expect(r.hooks).toBe(1);
        expect(r.version).toBe('4.46.0');
    });
});

describe('buildDigest + render + summarize', () => {
    it('producesCoherentDigest_andRenderableMarkdown', () => {
        writeJsonl(`${TEL}/command-usage.jsonl`, [
            { type: 'command_invocation', command: 'onboard', source: 'self-instrumented' },
            { type: 'gate_run', command: 'gate:test', outcome: 'success', duration_ms: 3963 },
        ]);
        writeJsonl(`${TEL}/hook-events.jsonl`, [
            { event: 'hook', name: 'memory-capture', outcome: 'success' },
            { event: 'hook', name: 'path-guardrail', outcome: 'success' },
        ]);
        writeJsonl(`${TEL}/skill-usage.jsonl`, [
            { type: 'agent_dispatch', agent: 'general-purpose', skills: ['systematic-debugging'] },
        ]);
        tmp.write(`${TEL}/_latest-summary.json`, JSON.stringify({ overall: true, mode: 'BUILD + TEST', stack: 'node', durationMs: 3963 }));
        tmp.write('docs/.output/memories/patterns/a.json', '{}');
        tmp.write('.claude/version.json', JSON.stringify({ version: '4.46.0' }));

        const d = buildDigest(tmp.root);
        expect(d.stack).toBe('node');
        expect(d.lastGate.overall).toBe(true);
        expect(d.commands.gates.lastDurationMs).toBe(3963);
        expect(d.hooks.rows).toBe(2);
        expect(d.agents.dispatches).toBe(1);
        expect(d.memoryStore.total).toBe(1);

        const md = renderMarkdown(d);
        expect(md).toContain('Telemetry Digest (automated)');
        expect(md).toContain('### Gate'); // gate section rendered
        expect(md).toContain('self-instrumented');

        const s = summarize(d);
        expect(s.template_version).toBe('4.46.0');
        expect(s.gate_runs).toBe(1);
        expect(s.memories).toBe(1);
    });

    it('emptyProject_doesNotThrow', () => {
        expect(() => buildDigest(tmp.root)).not.toThrow();
        const d = buildDigest(tmp.root);
        expect(() => renderMarkdown(d)).not.toThrow();
    });
});
