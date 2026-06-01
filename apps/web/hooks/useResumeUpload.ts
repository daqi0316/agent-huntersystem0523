import { useState, useRef } from "react";
import { toast } from "sonner";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB
const SUPPORTED_TYPES = ["pdf", "docx", "doc", "txt", "jpg", "png"];

export interface UploadedFile {
  file_url: string;
  filename: string;
  file_size: number;
  file_type: string;
}

interface UseResumeUploadReturn {
  uploading: boolean;
  progress: number;
  error: string | null;
  upload: (file: File) => Promise<UploadedFile | null>;
  clearError: () => void;
}

export function useResumeUpload(): UseResumeUploadReturn {
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const upload = async (file: File): Promise<UploadedFile | null> => {
    setError(null);

    const ext = file.name.split(".").pop()?.toLowerCase() || "";
    if (!SUPPORTED_TYPES.includes(ext)) {
      const msg = `不支持的文件格式 .${ext}，支持: ${SUPPORTED_TYPES.join(", ")}`;
      setError(msg);
      toast.error(msg);
      return null;
    }

    if (file.size > MAX_FILE_SIZE) {
      const msg = `文件过大，最大支持 ${MAX_FILE_SIZE / 1024 / 1024}MB`;
      setError(msg);
      toast.error(msg);
      return null;
    }

    setUploading(true);
    setProgress(10);

    try {
      const formData = new FormData();
      formData.append("file", file);

      setProgress(30);
      const res = await fetch(`${API_BASE}/file/upload`, {
        method: "POST",
        body: formData,
      });

      setProgress(80);
      const body = await res.json();

      if (!res.ok || body.error) {
        throw new Error(body.error || `上传失败 (${res.status})`);
      }

      setProgress(100);
      const result: UploadedFile = {
        file_url: body.file_url,
        filename: body.filename,
        file_size: body.file_size,
        file_type: ext,
      };
      toast.success(`${file.name} 上传成功`);
      return result;
    } catch (err) {
      const msg = err instanceof Error ? err.message : "上传失败";
      setError(msg);
      toast.error(msg);
      return null;
    } finally {
      setUploading(false);
      setTimeout(() => setProgress(0), 500);
    }
  };

  const clearError = () => setError(null);

  return { uploading, progress, error, upload, clearError };
}
