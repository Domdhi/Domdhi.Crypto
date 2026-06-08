// Tests for doc-drift.js — detection of legacy/duplicate planning docs (F2).

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { createRequire } from 'node:module';
import os from 'node:os';
import path from 'node:path';
import fs from 'node:fs';

const require = createRequire(import.meta.url);
const { detectDocDrift } = require('../doc-drift');

let root;
beforeEach(() => { root = fs.mkdtempSync(path.join(os.tmpdir(), 'doc-drift-')); });
afterEach(() => { fs.rmSync(root, { recursive: true, force: true }); });

function write(rel, content = '# real doc\n') {
    const p = path.join(root, rel);
    fs.mkdirSync(path.dirname(p), { recursive: true });
    fs.writeFileSync(p, content);
}

describe('detectDocDrift', () => {
    it('cleanRepo_noDrift', () => {
        write('docs/_project-architecture.md');
        write('docs/todo/_backlog.md');
        const r = detectDocDrift(root);
        expect(r.hasDrift).toBe(false);
        expect(r.legacy).toEqual([]);
        expect(r.duplicates).toEqual([]);
    });

    it('flagsLegacyDoc_andWhetherCanonicalAlsoExists', () => {
        write('docs/_architecture.md');            // legacy
        write('docs/_project-architecture.md');    // canonical also present → BOTH
        write('docs/_prd.md');                     // legacy, no canonical
        const r = detectDocDrift(root);
        expect(r.hasDrift).toBe(true);
        const arch = r.legacy.find(l => l.file === 'docs/_architecture.md');
        expect(arch.canonical).toBe('docs/_project-architecture.md');
        expect(arch.canonicalExists).toBe(true);
        const prd = r.legacy.find(l => l.file === 'docs/_prd.md');
        expect(prd.canonicalExists).toBe(false);
    });

    it('flagsDuplicateBasenameAcrossRootAndCanonical', () => {
        write('docs/_backlog.md');         // root (non-canonical)
        write('docs/todo/_backlog.md');    // canonical
        const r = detectDocDrift(root);
        expect(r.duplicates).toHaveLength(1);
        expect(r.duplicates[0].name).toBe('_backlog.md');
    });

    it('ignoresTemplateStubs', () => {
        // An unfilled scaffold stub is not real drift.
        write('docs/_architecture.md', '<!-- @@template -->\n# stub\n');
        const r = detectDocDrift(root);
        expect(r.hasDrift).toBe(false);
    });
});
