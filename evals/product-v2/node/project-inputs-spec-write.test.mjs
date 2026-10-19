import test from 'node:test';
import assert from 'node:assert/strict';
import { createProjectInputsModule } from '../../../build/frontend-node/app/product_v2/project-inputs.js';
import { emptyShotSpecFromShot } from '../../../build/frontend-node/app/product_v2/domain/index.js';

const SHA = 'a'.repeat(64);
const shot = { shot_id:'shot_infographic_benefits', template_id:'infographic_benefits', role_id:'infographic',
  label:'卖点信息图', intent:'呈现已确认特点', required:false, custom:false,
  dependencies:[{kind:'asset_role',role:'primary'}], fact_slot_ids:['signature_features'] };

async function fixture() {
  const legacy = { ...emptyShotSpecFromShot(shot), schema_version:1,
    print_intent:'selected', layout:'product_left_text_right', on_image_texts:[{
      text_id:'t1',text:'CERAMIC MUG',source_slot_id:'signature_features',source_slot_version:1,
      status:'confirmed',origin:'user',
    }] };
  const rows = [
    {kind:'suite_plan',document_id:'suite',version:1,payload:{schema_version:1,shots:[shot]}},
    {kind:'shot_spec',document_id:shot.shot_id,version:1,payload:structuredClone(legacy)},
  ];
  const latest = (kind,id)=>rows.filter(row=>row.kind===kind&&row.document_id===id)
    .sort((a,b)=>b.version-a.version)[0]||null;
  const repository = {documents:{
    getLatest:async(_pid,kind,id)=>structuredClone(latest(kind,id)),
    listLatest:async(_pid,kind)=>[...new Set(rows.filter(row=>row.kind===kind).map(row=>row.document_id))]
      .map(id=>structuredClone(latest(kind,id))),
    listVersions:async(_pid,kind,id)=>structuredClone(rows.filter(row=>row.kind===kind&&row.document_id===id)),
    save:async(_pid,input)=>{
      const head=latest(input.kind,input.documentId);
      if((head?.version||0)!==input.expectedVersion) throw new Error('version conflict');
      const row={kind:input.kind,document_id:input.documentId,version:(head?.version||0)+1,
        payload:structuredClone(input.payload)};
      rows.push(row);return structuredClone(row);
    },
  }};
  const action={projectId:'project-spec-writes',generation:1,alive:()=>true};
  const owner=createProjectInputsModule({repository,beginAction:()=>action,settings:{},capabilities:()=>null,
    projectIdReader:()=>action.projectId,projectNameReader:()=>'商品',
    draftInput:()=>({schema_version:1,product_name:'',description:'',selling_points:[],focus:'',references:[]})});
  await owner.restore(action);
  return {owner,rows,legacy,latest};
}

test('saving and restoring a published v1 spec writes current references and exact text provenance without changing old rows',async()=>{
  const {owner,rows,legacy}=await fixture();
  const original=structuredClone(rows[1]);
  await owner.saveShotSpec(shot.shot_id,{reference_sha256s:[SHA]});
  const saved=owner.shotSpecEntry(shot.shot_id);
  assert.equal(saved.spec.schema_version,2);
  assert.deepEqual(saved.spec.reference_sha256s,[SHA]);
  assert.deepEqual(saved.spec.on_image_texts,[{text_id:'t1',text:'CERAMIC MUG',status:'confirmed',origin:'user',
    source:{kind:'fact_slot',document_id:'signature_features',version:1}}]);
  assert.deepEqual(rows[1],original);
  assert.deepEqual(original.payload,legacy);
  await owner.restoreShotSpec(shot.shot_id);
  const restored=owner.shotSpecEntry(shot.shot_id);
  assert.equal(restored.version,3);
  assert.equal(restored.spec.schema_version,2);
  assert.equal(Object.hasOwn(restored.spec,'reference_sha256s'),false);
  assert.deepEqual(restored.spec.on_image_texts,saved.spec.on_image_texts);
  assert.deepEqual(rows[1],original);
});

test('inherit-clear and other changes remain atomic across a conflicting save, explicit reload and retry',async()=>{
  const {owner,rows,latest}=await fixture();
  await owner.saveShotSpec(shot.shot_id,{reference_sha256s:[SHA]});
  const prior=structuredClone(owner.shotSpecEntry(shot.shot_id));
  rows.push({...structuredClone(latest('shot_spec',shot.shot_id)),version:3});
  const changes={reference_sha256s:undefined,purpose:'完整呈现已确认特点'};
  const before=structuredClone(rows);
  await assert.rejects(()=>owner.saveShotSpec(shot.shot_id,changes),/version conflict/);
  assert.deepEqual(rows,before,'a failed combined save must not persist a reference-only intermediate version');
  assert.deepEqual(owner.shotSpecEntry(shot.shot_id),prior);
  await owner.reloadShotSpec(shot.shot_id);
  await owner.saveShotSpec(shot.shot_id,changes);
  const saved=owner.shotSpecEntry(shot.shot_id);
  assert.equal(saved.version,4);
  assert.equal(saved.spec.purpose,changes.purpose);
  assert.equal(Object.hasOwn(saved.spec,'reference_sha256s'),false);
  assert.deepEqual(rows.slice(0,before.length),before);
});
