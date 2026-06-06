"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

type Agreement = {
  type: string;
  version: string;
  title: string;
  url: string;
  required: boolean;
};

type AcceptanceStatus = {
  all_accepted: boolean;
  accepted: string[];
  missing: string[];
  required: string[];
};

export default function LegalAcceptPage() {
  const router = useRouter();
  const [agreements, setAgreements] = useState<Agreement[]>([]);
  const [status, setStatus] = useState<AcceptanceStatus | null>(null);
  const [checked, setChecked] = useState<Record<string, boolean>>({});
  const [submitting, setSubmitting] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.get<{ data: Agreement[] }>("/legal/agreements").then((r) => r.data || []),
      api.get<{ data: AcceptanceStatus }>("/legal/status").then((r) => r.data),
    ]).then(([a, s]) => {
      setAgreements(a);
      setStatus(s);
      setLoading(false);
    });
  }, []);

  async function acceptAll() {
    setSubmitting(true);
    try {
      for (const a of agreements) {
        if (!checked[a.type] || !a.required) continue;
        if (status?.accepted.includes(a.type)) continue;
        await api.post("/legal/accept", {
          agreement_type: a.type,
          confirm: true,
        });
      }
      const r = await api.get<{ data: AcceptanceStatus }>("/legal/status");
      setStatus(r.data);
      if (r.data?.all_accepted) {
        router.push("/");
      }
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) {
    return <div className="container mx-auto p-6">加载中...</div>;
  }

  return (
    <div className="container mx-auto p-6 max-w-2xl">
      <h1 className="text-2xl font-bold mb-2">协议接受</h1>
      <p className="text-gray-600 mb-6">
        继续使用前, 请阅读并接受以下协议。带 <span className="text-red-500">*</span> 为必勾项。
      </p>

      {status?.all_accepted && (
        <div className="mb-6 p-4 bg-green-50 border border-green-200 rounded text-green-800">
          ✅ 您已接受所有必勾协议, <a href="/" className="underline">返回主页</a>。
        </div>
      )}

      <div className="space-y-4">
        {agreements.map((a) => {
          const isAccepted = status?.accepted.includes(a.type) || false;
          return (
            <div key={a.type} className="border rounded p-4">
              <div className="flex items-start gap-3">
                <input
                  type="checkbox"
                  id={a.type}
                  disabled={isAccepted}
                  checked={isAccepted || checked[a.type] || false}
                  onChange={(e) => setChecked({ ...checked, [a.type]: e.target.checked })}
                  className="mt-1 w-5 h-5"
                />
                <div className="flex-1">
                  <label htmlFor={a.type} className="block font-medium cursor-pointer">
                    {a.title}
                    {a.required && <span className="text-red-500 ml-1">*</span>}
                    {isAccepted && (
                      <span className="ml-2 text-xs px-2 py-0.5 bg-green-100 text-green-700 rounded">
                        已接受
                      </span>
                    )}
                  </label>
                  <div className="text-sm text-gray-500 mt-1">
                    版本: {a.version}
                    {isAccepted && " · 当前最新版本"}
                  </div>
                  <a
                    href={a.url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-sm text-blue-600 hover:underline mt-1 inline-block"
                  >
                    查看完整协议 →
                  </a>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <div className="mt-8 flex gap-3">
        <button
          onClick={acceptAll}
          disabled={
            submitting ||
            status?.all_accepted ||
            agreements.filter((a) => a.required && !status?.accepted.includes(a.type))
              .some((a) => !checked[a.type])
          }
          className="px-6 py-3 bg-blue-600 text-white rounded font-semibold disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {submitting ? "提交中..." : status?.all_accepted ? "已接受全部" : "接受并继续"}
        </button>
        <a
          href="/help"
          className="px-6 py-3 border rounded text-gray-700"
        >
          暂不接受, 查看帮助
        </a>
      </div>
    </div>
  );
}
