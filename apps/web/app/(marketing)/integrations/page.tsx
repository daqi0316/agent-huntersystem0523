"use client";

import Link from "next/link";

const PLATFORMS = [
  {
    name: "微信服务号 + 企业微信",
    slug: "wechat",
    icon: "💬",
    setup_time: "5-10 工作日",
    cost: "免费 (需服务号认证 ¥300/年)",
    features: ["扫码登录", "模板消息推送", "小程序跳转", "公众号菜单"],
    steps: [
      "注册微信服务号 (已认证)",
      "启用「网页授权」+「模板消息」接口",
      "在服务号后台配置 OAuth 回调域名 (airecruit.com)",
      "提供 AppID + AppSecret 给运维",
      "我们后台配置 + 测试登录 + 测试模板发送",
    ],
    required_credentials: ["WECHAT_APP_ID", "WECHAT_APP_SECRET", "WECHAT_TEMPLATE_ID"],
    docs: "docs/oauth/wechat-oauth-design.md",
  },
  {
    name: "钉钉",
    slug: "dingtalk",
    icon: "📱",
    setup_time: "3-7 工作日",
    cost: "免费",
    features: ["扫码登录", "工作通知 (1 万人群)", "审批流", "视频会议"],
    steps: [
      "登录钉钉开放平台 https://open-dev.dingtalk.com",
      "创建「H5 微应用」",
      "配置回调域名 + 权限范围 (snsapi_login)",
      "提供 CorpID + AgentID + AppSecret",
      "我们后台配置 + 测试",
    ],
    required_credentials: ["DINGTALK_CORP_ID", "DINGTALK_AGENT_ID", "DINGTALK_APP_SECRET"],
    docs: "P6-8 OAuth 文档 (已 ship)",
  },
  {
    name: "飞书",
    slug: "feishu",
    icon: "🚀",
    setup_time: "3-7 工作日",
    cost: "免费",
    features: ["扫码登录", "群机器人", "多维表格", "云文档"],
    steps: [
      "登录飞书开放平台 https://open.feishu.cn",
      "创建「企业自建应用」",
      "配置回调域名 + 权限 (contact:user.id:readonly)",
      "提供 AppID + AppSecret",
      "我们后台配置 + 测试",
    ],
    required_credentials: ["FEISHU_APP_ID", "FEISHU_APP_SECRET"],
    docs: "P6-8 OAuth 文档 (已 ship)",
  },
  {
    name: "企业微信",
    slug: "wecom",
    icon: "🏢",
    setup_time: "5-10 工作日",
    cost: "免费 (需企业认证)",
    features: ["扫码登录", "客户联系", "审批", "汇报"],
    steps: [
      "登录企业微信管理后台 https://work.weixin.qq.com",
      "创建「自建应用」",
      "配置回调域名 + 可见范围",
      "提供 CorpID + AgentID + Secret",
      "我们后台配置 + 测试",
    ],
    required_credentials: ["WECOM_CORP_ID", "WECOM_AGENT_ID", "WECOM_SECRET"],
    docs: "P6-8 OAuth 文档 (已 ship)",
  },
];

export default function IntegrationsPage() {
  return (
    <div className="container mx-auto p-6 max-w-4xl">
      <h1 className="text-3xl font-bold mb-2">集成指南</h1>
      <p className="text-gray-600 mb-8">
        AI 招聘助手支持 4 大国内办公平台 OAuth 登录 + 消息推送, 申请 → 配置 → 上线 全流程。
      </p>

      <div className="grid gap-6">
        {PLATFORMS.map((p) => (
          <article key={p.slug} className="border rounded-lg p-6">
            <div className="flex items-start justify-between mb-4">
              <div className="flex items-center gap-3">
                <span className="text-3xl">{p.icon}</span>
                <div>
                  <h2 className="text-xl font-semibold">{p.name}</h2>
                  <p className="text-sm text-gray-500">
                    配置耗时: {p.setup_time} · 成本: {p.cost}
                  </p>
                </div>
              </div>
            </div>

            <div className="mb-4">
              <h3 className="text-sm font-semibold text-gray-500 mb-2">支持能力</h3>
              <div className="flex flex-wrap gap-2">
                {p.features.map((f) => (
                  <span key={f} className="px-2 py-1 bg-blue-50 text-blue-700 text-xs rounded">
                    {f}
                  </span>
                ))}
              </div>
            </div>

            <div className="mb-4">
              <h3 className="text-sm font-semibold text-gray-500 mb-2">配置步骤</h3>
              <ol className="text-sm space-y-1 list-decimal list-inside text-gray-700">
                {p.steps.map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ol>
            </div>

            <div className="mb-4">
              <h3 className="text-sm font-semibold text-gray-500 mb-2">需要提供的凭据</h3>
              <div className="flex flex-wrap gap-2">
                {p.required_credentials.map((c) => (
                  <code key={c} className="px-2 py-1 bg-gray-100 text-xs rounded font-mono">
                    {c}
                  </code>
                ))}
              </div>
            </div>

            <div className="text-xs text-gray-500">
              当前模式: <span className="font-mono">mock</span> · 真凭据配齐后 1 工作日内可启用
            </div>
          </article>
        ))}
      </div>

      <div className="mt-12 p-6 bg-gray-50 rounded-lg">
        <h2 className="text-xl font-bold mb-2">需要更多集成?</h2>
        <p className="text-gray-700 mb-4">
          我们的 roadmap 包括: 薪人薪事/北森 (HRIS) · 钉钉/飞书/企微 (审批流) · 招聘平台 (Boss直聘/拉勾)。
        </p>
        <a
          href="mailto:integrations@airecruit.com"
          className="text-blue-600 hover:underline"
        >
          → 申请新集成
        </a>
      </div>
    </div>
  );
}
