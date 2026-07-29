import { describe, it, expect } from 'vitest';

import {
  MATTER_LIFECYCLE_STAGES,
  HANDOFF_TRIGGERS,
  getConfidenceBand,
  slugify,
  createMatterId,
  normalizeMatterId,
  createOfficialRecordKey,
  getLifecycleStage,
  isReadyForMoneySweep,
  validatePreOfficialLanguage,
} from '@/lib/lifecycle';

// lifecycle.js encodes this app's editorial rules — when a signal may be called
// official, when it is ready to hand off to MoneySweep, and how a matter is
// identified. It is pure and had no tests; these cover the boundaries and the
// guarantees, not the happy path alone.

describe('getConfidenceBand', () => {
  it.each([
    [100, 'strong'],
    [95, 'strong'],
    [94, 'high'],
    [85, 'high'],
    [84, 'medium'],
    [70, 'medium'],
    [69, 'watch'],
    [50, 'watch'],
    [49, 'low'],
    [30, 'low'],
    [29, 'hold'],
    [0, 'hold'],
  ])('scores %i as %s', (score, tone) => {
    expect(getConfidenceBand(score).tone).toBe(tone);
  });

  it('treats a missing or unparseable score as the lowest band', () => {
    // Number(undefined) is NaN, so the `|| 0` fallback is what keeps an absent
    // score out of the "confirmed" band rather than throwing.
    expect(getConfidenceBand().tone).toBe('hold');
    expect(getConfidenceBand(null).tone).toBe('hold');
    expect(getConfidenceBand('not a number').tone).toBe('hold');
  });

  it('never returns a band without a label and description', () => {
    for (const score of [0, 30, 50, 70, 85, 95]) {
      const band = getConfidenceBand(score);
      expect(band.label).toBeTruthy();
      expect(band.description).toBeTruthy();
    }
  });
});

describe('slugify', () => {
  it('strips Spanish diacritics rather than dropping the characters', () => {
    // The corpus is Spanish-language, so this is the common case, not an edge one.
    expect(slugify('Oficialización')).toBe('oficializacion');
    expect(slugify('Añasco')).toBe('anasco');
    expect(slugify('Comisión de Auditoría')).toBe('comision-de-auditoria');
  });

  it('collapses runs of punctuation and trims leading/trailing dashes', () => {
    expect(slugify('  ¿Contrato — adjudicado?  ')).toBe('contrato-adjudicado');
    expect(slugify('a///b')).toBe('a-b');
  });

  it('returns an empty string for input with nothing slug-able', () => {
    expect(slugify('')).toBe('');
    expect(slugify('¿?—')).toBe('');
  });
});

describe('createMatterId', () => {
  it('builds a stable id from type, jurisdiction, date and title', () => {
    expect(
      createMatterId({
        matterType: 'contract',
        jurisdiction: 'pr',
        title: 'Contrato de energía',
        firstSeenAt: '2026-03-15T08:00:00Z',
      }),
    ).toBe('PR-CONTRACT-20260315-contrato-de-energia');
  });

  it('is deterministic — the same input yields the same id', () => {
    const input = { matterType: 'law', title: 'Ley 42', firstSeenAt: '2026-01-02' };
    expect(createMatterId(input)).toBe(createMatterId(input));
  });

  it('falls back rather than producing a malformed id', () => {
    expect(createMatterId({})).toBe('PR-MATTER-undated-untitled');
  });

  it('truncates the title segment to 48 characters', () => {
    const id = createMatterId({ title: 'a'.repeat(80), firstSeenAt: '2026-01-01' });
    expect(id.split('-').at(-1)).toHaveLength(48);
  });
});

describe('normalizeMatterId', () => {
  it('prefers an existing matter_id over deriving a new one', () => {
    expect(normalizeMatterId({ matter_id: '  PR-LAW-20260101-ley  ', title: 'ignored' }))
      .toBe('PR-LAW-20260101-ley');
  });

  it('derives one from whichever date field is present', () => {
    // The four date fields are tried in order; this pins that published_at is
    // used when first_seen_at is absent, so records from different sources
    // still get comparable ids.
    expect(normalizeMatterId({ title: 'Acta', published_at: '2026-05-06' }))
      .toBe('PR-MATTER-20260506-acta');
  });
});

describe('createOfficialRecordKey', () => {
  it('composes matter, type and identifier into one key', () => {
    expect(
      createOfficialRecordKey({
        matter_id: 'PR-LAW-20260101-ley',
        record_type: 'Ley',
        official_identifier: 'Ley 42-2026',
      }),
    ).toBe('PR-LAW-20260101-ley::ley::ley-42-2026');
  });

  it('distinguishes two records that differ only in identifier', () => {
    const base = { matter_id: 'PR-LAW-20260101-ley', record_type: 'ley' };
    expect(createOfficialRecordKey({ ...base, official_identifier: 'A' }))
      .not.toBe(createOfficialRecordKey({ ...base, official_identifier: 'B' }));
  });
});

describe('getLifecycleStage', () => {
  it('resolves a known stage key', () => {
    expect(getLifecycleStage('officialized').order).toBe(4);
  });

  it('falls back to public_signal for an unknown key', () => {
    // Falling back to order 1 — not 0 — matters: several rules branch on
    // `order >= 4`, so an unrecognised stage must not read as officialized.
    expect(getLifecycleStage('nonsense').key).toBe('public_signal');
    expect(getLifecycleStage(undefined).order).toBeLessThan(4);
  });

  it('keeps the stage order strictly ascending', () => {
    const orders = MATTER_LIFECYCLE_STAGES.map((s) => s.order);
    expect(orders).toEqual([...orders].sort((a, b) => a - b));
    expect(new Set(orders).size).toBe(orders.length);
  });
});

describe('isReadyForMoneySweep', () => {
  it('is ready when the matter carries a handoff trigger', () => {
    expect(isReadyForMoneySweep({ handoff_triggers: ['contract_awarded'] })).toBe(true);
  });

  it('is ready when a trigger arrives on a signal rather than the matter', () => {
    // Triggers are unioned across the matter and every signal, so evidence that
    // landed on a signal still promotes the matter.
    expect(isReadyForMoneySweep({}, [{ handoff_triggers: ['payment_issued'] }])).toBe(true);
  });

  it('is ready once an official identifier or source url exists', () => {
    expect(isReadyForMoneySweep({ official_identifier: 'Ley 42-2026' })).toBe(true);
    expect(isReadyForMoneySweep({ official_source_url: 'https://example.gov/doc' })).toBe(true);
  });

  it('is ready once the stage reaches officialized', () => {
    expect(isReadyForMoneySweep({ status_lifecycle: 'officialized' })).toBe(true);
  });

  it('is not ready for a bare early-stage matter', () => {
    expect(isReadyForMoneySweep({ status_lifecycle: 'public_signal' }, [])).toBe(false);
    expect(isReadyForMoneySweep()).toBe(false);
  });

  it('ignores a trigger that is not in the recognised vocabulary', () => {
    expect(isReadyForMoneySweep({ handoff_triggers: ['made_up_trigger'] })).toBe(false);
    expect(HANDOFF_TRIGGERS).not.toContain('made_up_trigger');
  });
});

describe('validatePreOfficialLanguage', () => {
  // This is the app's editorial safety rule: do not let copy assert that
  // something is official before a canonical record exists.

  it('blocks an official claim while the matter is pre-official', () => {
    const result = validatePreOfficialLanguage('El contrato adjudicado se firmó ayer', 'public_signal');
    expect(result.status).toBe('blocked_official_claim');
    expect(result.blocked_matches).toContain('contrato adjudicado');
  });

  it('matches the blocked phrase regardless of accents or case', () => {
    // The guard normalises both sides, so "AUDITORIA FINAL" without the accent
    // still trips "auditoría final" — otherwise the rule would be trivially
    // evadable by dropping a diacritic.
    const result = validatePreOfficialLanguage('AUDITORIA FINAL publicada', 'developing_matter');
    expect(result.status).toBe('blocked_official_claim');
    expect(result.blocked_matches).toContain('auditoría final');
  });

  it('downgrades to needs_review once the matter is officialized', () => {
    // Same text, later stage: the claim is now potentially true, so it is a
    // review prompt rather than a block.
    const result = validatePreOfficialLanguage('contrato adjudicado', 'officialized');
    expect(result.status).toBe('needs_review');
    expect(result.blocked_matches).toContain('contrato adjudicado');
  });

  it('passes ordinary pre-official language', () => {
    const result = validatePreOfficialLanguage('Propuesto y pendiente de verificación oficial');
    expect(result.status).toBe('clean');
    expect(result.blocked_matches).toEqual([]);
  });

  it('treats an unknown stage as pre-official rather than permitting the claim', () => {
    // Fails closed: an unrecognised stage must not become an escape hatch.
    expect(validatePreOfficialLanguage('permiso emitido', 'not-a-real-stage').status)
      .toBe('blocked_official_claim');
  });

  it('handles empty input without throwing', () => {
    expect(validatePreOfficialLanguage().status).toBe('clean');
  });
});
