"use client";

import { useEffect, useRef, useState } from "react";
import { Mic, Pause, Play, Square, Upload, FileAudio, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/trpc";

type RecorderState = "idle" | "recording" | "paused" | "stopped" | "uploading" | "uploaded" | "transcribing" | "transcribed";

interface RecordingResponse {
  id: string;
  interview_id: string;
  status: string;
  transcript_text?: string;
  file_size_bytes?: number;
  duration_seconds?: number;
}

interface InterviewRecorderProps {
  defaultInterviewId?: string;
}

export function InterviewRecorder({ defaultInterviewId = "" }: InterviewRecorderProps) {
  const [interviewId, setInterviewId] = useState(defaultInterviewId);
  const [consent, setConsent] = useState(false);
  const [state, setState] = useState<RecorderState>("idle");
  const [seconds, setSeconds] = useState(0);
  const [blob, setBlob] = useState<Blob | null>(null);
  const [recording, setRecording] = useState<RecordingResponse | null>(null);
  const [evaluationCreated, setEvaluationCreated] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const timerRef = useRef<number | null>(null);

  useEffect(() => setInterviewId(defaultInterviewId), [defaultInterviewId]);

  useEffect(() => {
    if (state !== "recording") {
      if (timerRef.current) window.clearInterval(timerRef.current);
      timerRef.current = null;
      return;
    }
    timerRef.current = window.setInterval(() => setSeconds((v) => v + 1), 1000);
    return () => {
      if (timerRef.current) window.clearInterval(timerRef.current);
    };
  }, [state]);

  const reset = () => {
    setState("idle");
    setSeconds(0);
    setBlob(null);
    setRecording(null);
    setEvaluationCreated(false);
    setError(null);
    chunksRef.current = [];
  };

  const start = async () => {
    setError(null);
    if (!interviewId.trim()) {
      setError("请先选择或填写面试 ID");
      return;
    }
    if (!consent) {
      setError("录音前必须确认已获得参与方同意");
      return;
    }
    if (typeof window === "undefined" || !navigator.mediaDevices || !window.MediaRecorder) {
      setError("当前浏览器不支持录音，请换用 Chrome / Edge 最新版");
      return;
    }
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const recorder = new MediaRecorder(stream, { mimeType: "audio/webm" });
    chunksRef.current = [];
    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) chunksRef.current.push(event.data);
    };
    recorder.onstop = () => {
      stream.getTracks().forEach((track) => track.stop());
      setBlob(new Blob(chunksRef.current, { type: "audio/webm" }));
      setState("stopped");
    };
    mediaRecorderRef.current = recorder;
    setSeconds(0);
    recorder.start();
    setState("recording");
  };

  const pause = () => {
    mediaRecorderRef.current?.pause();
    setState("paused");
  };

  const resume = () => {
    mediaRecorderRef.current?.resume();
    setState("recording");
  };

  const stop = () => mediaRecorderRef.current?.stop();

  const upload = async () => {
    if (!blob) return;
    setState("uploading");
    setError(null);
    const fd = new FormData();
    fd.append("file", blob, `interview-${interviewId}-${Date.now()}.webm`);
    fd.append("consent_confirmed", "true");
    fd.append("duration_seconds", String(seconds));
    try {
      const uploaded = await api.upload<RecordingResponse>(`/interviews/${interviewId}/recordings/upload`, fd);
      setRecording(uploaded);
      setEvaluationCreated(false);
      setState("uploaded");
      toast.success("录音已上传");
    } catch (e) {
      setState("stopped");
      setError(e instanceof Error ? e.message : "上传失败");
    }
  };

  const transcribe = async () => {
    if (!recording?.id) return;
    setState("transcribing");
    setError(null);
    try {
      const result = await api.post<RecordingResponse>(
        `/interviews/${interviewId}/recordings/${recording.id}/transcribe`,
        {},
      );
      setRecording(result);
      setEvaluationCreated(false);
      setState("transcribed");
      toast.success("转写完成");
    } catch (e) {
      setState("uploaded");
      setError(e instanceof Error ? e.message : "转写失败");
    }
  };

  const createEvaluation = async () => {
    if (!recording?.id || !recording.transcript_text) return;
    setError(null);
    try {
      await api.post(`/interviews/${interviewId}/recordings/${recording.id}/evaluation`, {
        candidate_name: "候选人",
        round: "R1",
      });
      setEvaluationCreated(true);
      toast.success("已基于转写文本生成面试评价");
    } catch (e) {
      setError(e instanceof Error ? e.message : "生成评价失败");
    }
  };

  const canStart = state === "idle" || state === "stopped" || state === "uploaded" || state === "transcribed";

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="flex items-center gap-2 text-base">
          <FileAudio className="h-4 w-4" />
          面试录音工作台
        </CardTitle>
        <Badge variant="outline">{state}</Badge>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 md:grid-cols-[1fr_auto]">
          <Input value={interviewId} onChange={(e) => setInterviewId(e.target.value)} placeholder="面试 ID" />
          <div className="text-sm text-muted-foreground md:text-right">录音时长：{seconds}s</div>
        </div>

        <label className="flex items-start gap-2 text-sm text-muted-foreground">
          <input type="checkbox" className="mt-1" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
          已告知并获得面试参与方同意，允许为本次面试录音并用于转写/评估。
        </label>

        {error && <div className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</div>}

        <div className="flex flex-wrap gap-2">
          {canStart && (
            <Button onClick={start} className="gap-1" disabled={!consent || !interviewId.trim()}>
              <Mic className="h-4 w-4" /> 开始录音
            </Button>
          )}
          {state === "recording" && <Button variant="outline" onClick={pause} className="gap-1"><Pause className="h-4 w-4" /> 暂停</Button>}
          {state === "paused" && <Button variant="outline" onClick={resume} className="gap-1"><Play className="h-4 w-4" /> 继续</Button>}
          {(state === "recording" || state === "paused") && <Button variant="destructive" onClick={stop} className="gap-1"><Square className="h-4 w-4" /> 停止</Button>}
          {state === "stopped" && <Button onClick={upload} className="gap-1"><Upload className="h-4 w-4" /> 上传录音</Button>}
          {state === "uploaded" && <Button onClick={transcribe} className="gap-1"><FileAudio className="h-4 w-4" /> 开始转写</Button>}
          {recording?.transcript_text && !evaluationCreated && (
            <Button variant="outline" onClick={createEvaluation} className="gap-1">
              <FileAudio className="h-4 w-4" /> 生成面试评价
            </Button>
          )}
          {(state === "uploading" || state === "transcribing") && <Button disabled className="gap-1"><Loader2 className="h-4 w-4 animate-spin" /> 处理中</Button>}
          {state !== "recording" && state !== "paused" && <Button variant="ghost" onClick={reset}>重置</Button>}
        </div>

        {recording && (
          <div className="rounded-md border bg-muted/30 p-3 text-sm">
            <div>录音记录：{recording.id}</div>
            <div>状态：{recording.status}</div>
            {recording.file_size_bytes ? <div>大小：{Math.round(recording.file_size_bytes / 1024)} KB</div> : null}
          </div>
        )}

        {recording?.transcript_text && (
          <div className="rounded-md border p-3">
            <div className="mb-2 text-sm font-medium">转写文本</div>
            <p className="whitespace-pre-wrap text-sm text-muted-foreground">{recording.transcript_text}</p>
            {evaluationCreated && <div className="mt-2 text-sm text-green-600">已生成并保存面试评价。</div>}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
