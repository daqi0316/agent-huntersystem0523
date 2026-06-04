/**
 * 工具名 → 中文标签 映射
 * 跨 context-bar / data-card-parser / use-agent-event-stream 共用
 */

export const TOOL_LABELS: Record<string, string> = {
  get_dashboard_stats: "看板数据",
  search_candidates: "搜索候选人",
  screen_resume: "简历评估",
  generate_jd: "生成 JD",
  schedule_interview: "安排面试",
  get_schedule: "查询日程",
  get_upcoming_interviews: "即将面试",
  create_candidate: "创建候选人",
  update_candidate: "更新候选人",
  archive_candidate: "归档候选人",
  create_job: "创建职位",
  update_job: "更新职位",
  close_job: "关闭职位",
  cancel_interview: "取消面试",
  reschedule_interview: "改期面试",
  save_evaluation: "保存评估",
};

export function toolLabel(name: string | undefined): string {
  if (!name) return "";
  return TOOL_LABELS[name] || name;
}
