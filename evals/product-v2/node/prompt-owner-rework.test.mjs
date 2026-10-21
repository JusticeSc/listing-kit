import test from 'node:test';
import assert from 'node:assert/strict';
import { createPromptModule } from '../../../build/frontend-node/app/product_v2/prompts.js';
import { CORE_SLOT_REGISTRY, buildReworkDirective, emptyStyleSpec, emptyShotSpecFromShot } from '../../../build/frontend-node/app/product_v2/domain/index.js';
import { IMAGE_PROMPT_PROFILE } from './harness-core.mjs';

const PRODUCT_SHA = 'a'.repeat(64);
const CANDIDATE_SHA = 'e'.repeat(64);
const AT = '2026-10-19T08:00:00Z';

function fixture() {
  const shot = { shot_id: 'shot_main_clean', template_id: 'main_clean', role_id: 'main',
    label: '主图', intent: '完整展示商品主体', required: true, custom: false,
    dependencies: [{kind:'asset_role',role:'primary'}], fact_slot_ids: [] };
  const facts = { product_name: '玻璃罐', product_category: '收纳罐', signature_features: ['蜂窝纹理'] };
  const source = { projectId:'project-prompt-owner', projectName:'玻璃罐',
    slots: CORE_SLOT_REGISTRY.filter(item=>Object.hasOwn(facts,item.slot_id)).map(item=>({version:1,slot:{
      ...item,schema_version:1,authority:'core_fixed',value:facts[item.slot_id],source:'user_input',
      status:'confirmed',confidence:null,evidence:[],depends_on:[],
    }})),
    suitePlan:{schema_version:1,shots:[shot]},suiteVersion:1,
    styleSpec:{...emptyStyleSpec(),presentation:{appearance_state:'as_shown',contents_state:'not_applicable'}},styleVersion:1,
    shotSpecs:{[shot.shot_id]:{spec:emptyShotSpecFromShot(shot),version:1}},
    references:[{role:'primary',sha256:PRODUCT_SHA}],sellingPoints:[],intakeVersion:1,
  };
  const rows = [];
  const repository = {documents:{save:async(_project,input)=>{
    assert.equal(input.kind,'prompt_version');
    assert.equal(input.expectedVersion,rows.length,'the owner must append from its observed version');
    const row={version:rows.length+1,payload:structuredClone(input.payload)};
    rows.push(row);return structuredClone(row);
  }}};
  const action={projectId:source.projectId,generation:1,alive:()=>true};
  const environment={contract:'v2.4.1',provider:{provider_id:IMAGE_PROMPT_PROFILE.provider_id,
    model_id:IMAGE_PROMPT_PROFILE.model_id,capability_version:1,capabilities:{request_profile:IMAGE_PROMPT_PROFILE}}};
  const owner=createPromptModule({repository,beginAction:()=>action,sources:()=>source,imageEnvironment:()=>environment});
  const candidate={candidate_id:'candidate-to-edit',shot_id:shot.shot_id,asset_sha256:CANDIDATE_SHA,
    media_type:'image/png',width:1600,height:1600,created_at:AT};
  const directive=(mode,id='directive-owner-rework')=>buildReworkDirective({directiveId:id,
    shotId:shot.shot_id,mode,candidate,candidateDocument:{document_id:shot.shot_id,version:3},
    problems:['composition'],direction:'保持商品不变，仅把主体居中。',at:AT});
  return {owner,shot,rows,directive,source};
}

test('manual editing and reconfirming a rework prompt retains the fixed candidate before product evidence',async()=>{
  const {owner,shot,rows,directive}=fixture();
  await owner.compileAndSave(shot.shot_id,{rework:directive('edit_candidate')});
  const original=structuredClone(rows[0]);
  const editedText=owner.entryOf(shot.shot_id).record.compiled.text+'\n保留完整商品轮廓。';
  await owner.edit(shot.shot_id,editedText,'只补充商品边界要求');
  let record=owner.entryOf(shot.shot_id).record;
  assert.equal(record.compiled.text,editedText);
  assert.equal(record.request_snapshot.prompt,editedText);
  assert.deepEqual(record.request_snapshot.references.map(item=>item.sha256),[CANDIDATE_SHA,PRODUCT_SHA]);
  assert.deepEqual(record.request_snapshot.references[0].sources,[{kind:'candidate',document_id:shot.shot_id,version:3,asset_sha256:CANDIDATE_SHA}]);
  assert.equal(record.origin,'manual_edit');
  await owner.reconfirm(shot.shot_id,editedText);
  record=owner.entryOf(shot.shot_id).record;
  assert.equal(owner.entryOf(shot.shot_id).version,3);
  assert.equal(record.compiled.text,editedText);
  assert.deepEqual(record.request_snapshot.references.map(item=>item.sha256),[CANDIDATE_SHA,PRODUCT_SHA]);
  assert.deepEqual(rows[0],original,'new manual versions must not rewrite the original frozen action');
});

test('explicit keep-manual rework freezes each selected mode without rewriting text or older versions',async()=>{
  const {owner,shot,rows,directive}=fixture();
  await owner.compileAndSave(shot.shot_id);
  const manualText=owner.entryOf(shot.shot_id).record.compiled.text+'\n保留完整商品轮廓。';
  await owner.edit(shot.shot_id,manualText,'保留人工完整表达');
  const manual=structuredClone(rows[1]);
  const editDirective=directive('edit_candidate','directive-keep-edit');
  const preview=await owner.previewManualForRework(shot.shot_id,{rework:editDirective});
  assert.equal(preview.compiled.text,manualText);
  assert.equal(preview.payload.request_snapshot.prompt,manualText);
  assert.deepEqual(preview.references.map(item=>item.sha256),[CANDIDATE_SHA,PRODUCT_SHA]);
  assert.equal(rows.length,2,'preview must not append a prompt version');
  await owner.rebaseManualForRework(shot.shot_id,{rework:editDirective});
  const edit=owner.entryOf(shot.shot_id).record;
  assert.equal(edit.hash,preview.payload.hash,'the saved request must match the previewed manual request');
  assert.equal(edit.compiled.text,preview.compiled.text);
  assert.equal(edit.compiled.text,manualText);
  assert.equal(edit.request_snapshot.prompt,manualText);
  assert.equal(edit.basis.rework.mode,'edit_candidate');
  assert.deepEqual(edit.request_snapshot.references.map(item=>item.sha256),[CANDIDATE_SHA,PRODUCT_SHA]);
  await owner.rebaseManualForRework(shot.shot_id,{rework:directive('regenerate_original','directive-keep-original')});
  const regenerate=owner.entryOf(shot.shot_id).record;
  assert.equal(regenerate.compiled.text,manualText);
  assert.equal(regenerate.basis.rework.mode,'regenerate_original');
  assert.deepEqual(regenerate.request_snapshot.references.map(item=>item.sha256),[PRODUCT_SHA]);
  assert.deepEqual(rows[1],manual);
  assert.deepEqual(rows[2].payload,edit);
});

for (const mode of ['edit_candidate', 'regenerate_original']) {
  test(`repreparing and discarding a manual override preserves the fixed ${mode} source`, async () => {
    const {owner,shot,rows,directive,source}=fixture();
    const rework=directive(mode);
    await owner.compileAndSave(shot.shot_id,{rework});
    // 真实历史系统稿只有 compiled.rework.direction；当前 writer 会回填 basis 的同一方向。
    delete owner.entryOf(shot.shot_id).record.basis.rework.direction;
    delete rows[0].payload.basis.rework.direction;
    const original=structuredClone(rows[0]);
    const expectedLineage={...original.payload.basis.rework,direction:rework.direction};
    source.styleSpec.lighting='左侧柔和漫射光';
    source.styleVersion+=1;

    const result=await owner.prepare(new Map());
    assert.deepEqual(result,{prepared:1,errors:[]});
    const refreshed=owner.entryOf(shot.shot_id).record;
    assert.deepEqual(refreshed.basis.rework,expectedLineage);
    assert.deepEqual(refreshed.request_snapshot.references.map(item=>item.sha256),
      mode==='edit_candidate'?[CANDIDATE_SHA,PRODUCT_SHA]:[PRODUCT_SHA]);
    assert.equal(refreshed.request_snapshot.prompt,refreshed.compiled.text);
    assert.match(refreshed.compiled.text,/左侧柔和漫射光/);
    await owner.compileAndSave(shot.shot_id);
    const explicit=owner.entryOf(shot.shot_id).record;
    assert.deepEqual(explicit.basis.rework,expectedLineage,
      'the explicit local-prepare button must preserve the same source as automatic preparation');
    assert.deepEqual(explicit.request_snapshot.references,refreshed.request_snapshot.references);

    const manualText=explicit.compiled.text+'\n保留完整商品轮廓。';
    await owner.edit(shot.shot_id,manualText,'只补充商品边界要求');
    const manual=structuredClone(rows.at(-1));
    source.styleSpec.lighting='右侧柔和漫射光';
    source.styleVersion+=1;
    const discarded=await owner.discard(shot.shot_id);
    assert.notEqual(discarded.origin,'manual_edit');
    assert.deepEqual(discarded.basis.rework,expectedLineage,
      'discarding manual wording must not discard the restored system prompt source');
    assert.deepEqual(discarded.request_snapshot.references,explicit.request_snapshot.references);
    assert.match(discarded.compiled.text,/右侧柔和漫射光/);
    assert.equal(discarded.compiled.text.endsWith('\n保留完整商品轮廓。'),false);
    assert.deepEqual(rows.at(-2),manual,'discard must preserve the prior manual version');
    assert.deepEqual(rows[0],original,'refresh must preserve the original frozen prompt');
  });
}
