import test from 'node:test';
import assert from 'node:assert/strict';
import { evaluateSuiteFindings } from '../../../app/product_v2/domain/suite-review.js';

function dependencies(required = false, candidateId = null) {
  const common = { role_id: 'primary', role_label: '商品主图', custom: true,
    template_id: null, fact_slot_ids: [], intent: '展示商品' };
  const suitePlan = { schema_version: 1, shots: [
    { ...common, shot_id: 'shot_main', label: '主图', required: true, dependencies: [] },
    { ...common, shot_id: 'shot_size', label: '尺寸图', required,
      dependencies: [{ kind: 'fact', slot_id: 'size_dimensions' }] },
  ] };
  const selectionSet = { entries: [
    { shot_id: 'shot_main', required: true, state: 'current', candidate_id: 'candidate-main' },
    { shot_id: 'shot_size', required, state: candidateId ? 'current' : 'none', candidate_id: candidateId },
  ] };
  return evaluateSuiteFindings({ suitePlan, selectionSet, context: { facts: [], assets: [] } })
    .findings.find(finding => finding.rule_id === 'suite.dependency_satisfied');
}

test('unselected optional dimensions draft does not block adopted main image delivery', () => {
  const finding = dependencies();
  assert.equal(finding.severity, 'PASS');
  assert.deepEqual(finding.affected_shot_ids, []);
});

test('required or adopted dimensions still require confirmed dimensions', () => {
  for (const [required, candidateId] of [[true, null], [false, 'candidate-size']]) {
    const finding = dependencies(required, candidateId);
    assert.equal(finding.severity, 'BLOCK');
    assert.deepEqual(finding.affected_shot_ids, ['shot_size']);
  }
});
