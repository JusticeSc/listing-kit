import { readFile, writeFile } from 'node:fs/promises';
import { createPromptModule } from '../../build/frontend-node/app/product_v2/prompts.js';
import { createProjectInputsModule, projectSourcesFromSnapshot } from '../../build/frontend-node/app/product_v2/project-inputs.js';
import { buildReworkDirective, emptyStyleSpec, emptyShotSpecFromShot } from '../../build/frontend-node/app/product_v2/domain/index.js';
import { IMAGE_PROMPT_PROFILE } from '../../evals/product-v2/node/harness-core.mjs';

const archived = JSON.parse(await readFile(new URL('../full-product-start-20261018T140710Z/baseline-import-store.json', import.meta.url), 'utf8'));
const originalDocs = archived.stores.find(item => item.name === 'documents').rows;
const project = archived.stores.find(item => item.name === 'projects').rows[0];
const docs = structuredClone(originalDocs.filter(item => item.kind !== 'prompt_version'));
const projectId = project.project_id;
const latest = (kind, id) => docs.filter(item => item.kind === kind && item.document_id === id).sort((a,b)=>b.version-a.version)[0] || null;
const writes = [];
const repository = { documents: {
  getLatest: async (_project, kind, id) => structuredClone(latest(kind, id)),
  listLatest: async (_project, kind) => [...new Set(docs.filter(item=>item.kind===kind).map(item=>item.document_id))].map(id=>structuredClone(latest(kind,id))),
  listVersions: async (_project, kind, id) => structuredClone(docs.filter(item=>item.kind===kind && item.document_id===id)),
  save: async (_project, item) => {
    const previous = latest(item.kind,item.documentId);
    if ((previous?.version || 0) !== item.expectedVersion) throw new Error('Unexpected audit fixture OCC conflict');
    const row = { project_id:projectId, kind:item.kind, document_id:item.documentId, version:(previous?.version || 0)+1, payload:structuredClone(item.payload) };
    docs.push(row); writes.push({kind:row.kind, document_id:row.document_id, version:row.version}); return structuredClone(row);
  },
} };
const action = {projectId, alive:()=>true};
const source = projectSourcesFromSnapshot({project,documents:originalDocs});
const shot = source.suitePlan.shots.find(item=>item.role_id==='main');
if (!shot) throw new Error('Archived product has no main shot');
source.styleSpec = {...emptyStyleSpec(),presentation:{appearance_state:'as_shown',contents_state:'not_applicable'}};
source.shotSpecs[shot.shot_id] = {spec:emptyShotSpecFromShot(shot),version:1};
const environment = {contract:'v2.4.1',provider:{provider_id:IMAGE_PROMPT_PROFILE.provider_id,model_id:IMAGE_PROMPT_PROFILE.model_id,capability_version:1,capabilities:{request_profile:IMAGE_PROMPT_PROFILE}}};
const prompts = createPromptModule({repository,beginAction:()=>action,sources:()=>source,imageEnvironment:()=>environment});
const candidate = {candidate_id:'audit-problem-candidate',shot_id:shot.shot_id,asset_sha256:'e'.repeat(64),media_type:'image/png',width:1600,height:1600,attempt_action_id:'audit-original-action',created_at:'2026-10-19T08:00:00Z'};
const rework = buildReworkDirective({directiveId:'audit-rework-current',shotId:shot.shot_id,mode:'edit_candidate',candidate,candidateDocument:{document_id:shot.shot_id,version:1},problems:['composition'],direction:'保持商品不变，仅调整主体居中。',at:'2026-10-19T08:01:00Z'});
await prompts.compileAndSave(shot.shot_id);
const initialText = prompts.entryOf(shot.shot_id).record.compiled.text;
await prompts.edit(shot.shot_id,initialText+'\n人工补充：保留商品完整轮廓。','核对人工全文保留路径');
const manualText = prompts.entryOf(shot.shot_id).record.compiled.text;
const rebased = await prompts.rebaseManualForRework(shot.shot_id,{rework});
const rebasedRecord = prompts.entryOf(shot.shot_id).record;
const observations = {
  boundary:'Isolated in-memory repository, real compiled product owners; no browser, storage mutation, HTTP or model call. First finding verifies the saved shape used by the actual generation reread predicate, not a full generation submission.',
  keep_manual:{saved_version:rebased.saved.version,text_preserved:rebasedRecord.compiled.text===manualText,basis_rework_directive:rebasedRecord.basis.rework?.directive_id,compiled_rework:rebasedRecord.compiled.rework || null,generation_reread_predicate_can_match:Boolean(rebasedRecord.compiled.rework?.directive_id===rework.directive_id)},
};
await prompts.compileAndSave(shot.shot_id,{rework});
const beforeEdit = writes.length;
try { await prompts.edit(shot.shot_id,manualText,'核对返工后的人工编辑'); observations.edit_rework={unexpectedly_saved:true}; }
catch(error) { observations.edit_rework={message:error.message,writes_during_failed_edit:writes.length-beforeEdit}; }
// 明确种入一个合法已发布v1规格，避免把归档中尚无规格的新图误当既有v1项目。
docs.push({project_id:projectId,kind:'shot_spec',document_id:shot.shot_id,version:1,payload:{...emptyShotSpecFromShot(shot),schema_version:1}});
const inputs = createProjectInputsModule({repository,beginAction:()=>action,settings:{},capabilities:()=>null,projectIdReader:()=>projectId,projectNameReader:()=>project.name,draftInput:()=>({schema_version:1,product_name:'',description:'',selling_points:[],focus:'',references:[]})});
await inputs.restore(action);
observations.existing_spec={schema_version:inputs.shotSpecEntry(shot.shot_id)?.spec.schema_version};
const beforeSpec = writes.length;
try { await inputs.saveShotSpec(shot.shot_id,{reference_sha256s:[source.references[0].sha256]}); observations.existing_spec.unexpectedly_saved=true; }
catch(error) { observations.existing_spec.message=error.message; observations.existing_spec.writes_during_failed_save=writes.length-beforeSpec; }
observations.findings_reproduced = observations.keep_manual.text_preserved && !observations.keep_manual.generation_reread_predicate_can_match && /第一张图/.test(observations.edit_rework.message || '') && observations.edit_rework.writes_during_failed_edit===0 && observations.existing_spec.schema_version===1 && /reference_sha256s/.test(observations.existing_spec.message || '') && observations.existing_spec.writes_during_failed_save===0;
console.log(JSON.stringify(observations,null,2));
await writeFile(new URL('./owner-gap-observations.json', import.meta.url),JSON.stringify(observations,null,2)+'\n');
if (!observations.findings_reproduced) process.exitCode=1;
