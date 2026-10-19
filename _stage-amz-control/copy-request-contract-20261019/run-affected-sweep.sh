#!/usr/bin/env bash
# 本批（文案提议请求合同 + 商品资料版本过期判据）改动后的定向复核：
# prompt 记录/依据/确认单/选择/交付/项目包 相关验证器，顺序执行、逐条记 rc。
# 不含 2_4_1（全库 manifest 断言）与 2_7_1（两轮聚合门，留给最终冻结候选）。
set -u
cd "$(dirname "$0")/../.." || exit 1
out=_stage-amz-control/copy-request-contract-20261019
py=.venv/Scripts/python.exe
[ -x "$py" ] || py=.venv/bin/python
: > "$out/affected-sweep-summary.txt"
for tool in verify_v2_2_3_intake_understanding \
            verify_v2_3_4_prompt_compiler verify_v2_3_5_pre_generation_confirm \
            verify_v2_3_6_prompt_manual_edit verify_v2_3_7_copy_adoption_chain \
            verify_v2_4_2_generation_attempt \
            verify_v2_4_3_batch_execution verify_v2_5_1_deterministic_review \
            verify_v2_5_3_compare_panel verify_v2_5_4_rework_loop \
            verify_v2_5_5_suite_review verify_v2_6_1_selection verify_v2_6_2_delivery \
            verify_v2_6_3_project_transfer verify_v2_1_2_project_home \
            verify_v2_1_3_project_package verify_v2_ui_2_interaction_visual \
            verify_v2_ui_3_frontend verify_v2_packet08_settings_vision \
            verify_v2_packet08_adoption_ai verify_v2_packet08_delivery_ai; do
  start=$SECONDS
  "$py" "tools/$tool.py" > "$out/affected-$tool.out" 2>&1
  rc=$?
  printf '%-48s rc=%d %ds\n' "$tool" "$rc" "$((SECONDS - start))" | tee -a "$out/affected-sweep-summary.txt"
done
