import test from 'node:test';
import assert from 'node:assert';
import { mergeWithSampleBaseline } from '../src/utils/mergeBaseline.js';

test('mergeWithSampleBaseline preserves genuine ReliefWeb reports without [SAMPLE DEMO]', () => {
  const baseMock = {
    reliefweb: {
      queried: true,
      status: 'success',
      matched_reports: [
        {
          id: 'mock-1',
          title: 'Mock Baseline Sitrep',
          source: 'Mock Source',
          published_date: '2018-08-10',
        },
      ],
    },
  };

  const liveData = {
    reliefweb: {
      queried: true,
      status: 'success',
      matched_reports: [
        {
          report_id: '2766664',
          title: 'AMDA Activity Report #4: Emergency Relief for Flood Victims in Kerala State, India',
          url: 'https://reliefweb.int/node/2766664',
          publication_date: '2018-08-31T00:00:00+00:00',
          sources: ['Association of Medical Doctors of Asia'],
          body_snippet: 'Emergency distribution...',
        },
      ],
      total_reports_found: 108,
    },
  };

  const merged = mergeWithSampleBaseline(baseMock, liveData);
  const reports = merged.reliefweb.matched_reports;

  assert.strictEqual(reports.length, 1);
  assert.strictEqual(reports[0].title, 'AMDA Activity Report #4: Emergency Relief for Flood Victims in Kerala State, India');
  assert.strictEqual(reports[0].title.includes('[SAMPLE DEMO]'), false);
  assert.strictEqual(reports[0].source, 'Association of Medical Doctors of Asia');
  assert.strictEqual(reports[0].source.includes('(Sample Demo)'), false);
  assert.strictEqual(reports[0].date, '2018-08-31');
});

test('mergeWithSampleBaseline does NOT inject mock [SAMPLE DEMO] when live ReliefWeb query legitimately returns 0 reports', () => {
  const baseMock = {
    reliefweb: {
      queried: true,
      status: 'success',
      matched_reports: [
        {
          id: 'mock-lucknow',
          title: 'India: Uttar Pradesh Monsoon Overflow & Urban Flood Preparedness Report',
          source: 'State Disaster Management Authority / UN OCHA',
          published_date: '2026-10-02',
        },
      ],
    },
  };

  const liveData = {
    reliefweb: {
      queried: true,
      status: 'no_matching_reports',
      matched_reports: [],
      total_reports_found: 13,
      unmatched_reports_count: 10,
    },
  };

  const merged = mergeWithSampleBaseline(baseMock, liveData);
  const reports = merged.reliefweb.matched_reports;

  // Genuine zero-match live state must be preserved as empty array, NOT replaced with mock [SAMPLE DEMO]
  assert.strictEqual(reports.length, 0);
  assert.deepStrictEqual(reports, []);
});

test('mergeWithSampleBaseline preserves [SAMPLE DEMO] fallback when live ReliefWeb feed is actually unavailable (error)', () => {
  const baseMock = {
    reliefweb: {
      queried: true,
      status: 'success',
      matched_reports: [
        {
          id: 'mock-1',
          title: 'Mock Baseline Sitrep',
          source: 'Mock Source',
          published_date: '2018-08-10',
        },
      ],
    },
  };

  const liveData = {
    reliefweb: {
      queried: true,
      status: 'error',
      error_message: 'ReliefWeb API HTTP 500: Server Error',
      matched_reports: [],
    },
  };

  const merged = mergeWithSampleBaseline(baseMock, liveData);
  const reports = merged.reliefweb.matched_reports;

  assert.strictEqual(reports.length, 1);
  assert.strictEqual(reports[0].title, '[SAMPLE DEMO] Mock Baseline Sitrep');
  assert.strictEqual(reports[0].source, 'Mock Source (Sample Demo)');
});

test('mergeWithSampleBaseline preserves [SAMPLE DEMO] fallback when live ReliefWeb feed is unqueried / disabled', () => {
  const baseMock = {
    reliefweb: {
      queried: true,
      status: 'success',
      matched_reports: [
        {
          id: 'mock-1',
          title: 'Mock Baseline Sitrep',
          source: 'Mock Source',
          published_date: '2018-08-10',
        },
      ],
    },
  };

  const liveData = {
    reliefweb: {
      queried: false,
      status: 'disabled',
      matched_reports: [],
    },
  };

  const merged = mergeWithSampleBaseline(baseMock, liveData);
  const reports = merged.reliefweb.matched_reports;

  assert.strictEqual(reports.length, 1);
  assert.strictEqual(reports[0].title, '[SAMPLE DEMO] Mock Baseline Sitrep');
});
