"use client";

import { useState } from "react";

const FAQ: { q: string; a: string; cat: string }[] = [
  {
    cat: "产品使用",
    q: "支持哪些简历格式?",
    a: "PDF / Word (.docx) / 图片 (jpg/png) / 纯文本粘贴。",
  },
  {
    cat: "产品使用",
    q: "AI 评估依据是什么?",
    a: "评估依据 + 关键能力维度 + 置信度均向 HR 公开, 不可识别性别/民族/年龄等受保护属性。详见隐私政策。",
  },
  {
    cat: "产品使用",
    q: "候选人对 AI 评分有异议怎么办?",
    a: "候选人 7 天内可申诉, 48h 内人工复核。",
  },
  {
    cat: "计费",
    q: "试用是免费的吗?",
    a: "14 天全功能免费, 无需信用卡。试用结束前 3 天提醒, 降级不扣款。",
  },
  {
    cat: "计费",
    q: "价格多少?",
    a: "SMB ¥299/月起, Enterprise ¥1999/月起, 定制请询 sales@airecruit.com。",
  },
  {
    cat: "计费",
    q: "不满意能退吗?",
    a: "7 天无理由退款 (订阅周期内)。",
  },
  {
    cat: "数据合规",
    q: "我的数据存在哪?",
    a: "全部中国境内 (北京/上海/广州阿里云), 不向境外传输。",
  },
  {
    cat: "数据合规",
    q: "等保几级?",
    a: "在办等保三级 (2026 Q4 取证)。",
  },
  {
    cat: "集成",
    q: "支持钉钉/飞书/企微吗?",
    a: "钉钉已上线 (mock 模式, 真凭据需用户申请), 飞书/企微同模式, 申请后 1 周内可启用。",
  },
  {
    cat: "故障",
    q: "怎么看服务状态?",
    a: "https://status.airecruit.com (实时)",
  },
];

const CATS = Array.from(new Set(FAQ.map((f) => f.cat)));

export default function HelpPage() {
  const [active, setActive] = useState<string | null>(null);

  return (
    <div className="container mx-auto p-6 max-w-3xl">
      <h1 className="text-3xl font-bold mb-2">帮助中心</h1>
      <p className="text-gray-600 mb-8">
        常见问题 + 工单入口。找不到答案请 <a href="/support" className="text-blue-600 hover:underline">提交工单</a>。
      </p>

      {CATS.map((cat) => (
        <section key={cat} className="mb-8">
          <h2 className="text-xl font-semibold mb-3">{cat}</h2>
          <div className="space-y-2">
            {FAQ.filter((f) => f.cat === cat).map((f, i) => {
              const key = `${cat}-${i}`;
              return (
                <div key={key} className="border rounded">
                  <button
                    onClick={() => setActive(active === key ? null : key)}
                    className="w-full text-left p-3 hover:bg-gray-50 flex items-center justify-between"
                  >
                    <span className="font-medium">{f.q}</span>
                    <span className="text-gray-400">{active === key ? "−" : "+"}</span>
                  </button>
                  {active === key && (
                    <div className="p-3 pt-0 text-gray-700 border-t">{f.a}</div>
                  )}
                </div>
              );
            })}
          </div>
        </section>
      ))}

      <div className="mt-12 p-6 bg-blue-50 rounded-lg text-center">
        <h2 className="text-xl font-bold mb-2">还没解决?</h2>
        <a
          href="/support"
          className="inline-block px-6 py-3 bg-blue-600 text-white rounded font-semibold"
        >
          提交工单
        </a>
      </div>
    </div>
  );
}
