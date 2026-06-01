"use client";

import { useCallback, useState } from "react";
import { Upload, X, Loader2, FileText, Image, File } from "lucide-react";
import { useResumeUpload, UploadedFile } from "@/hooks/useResumeUpload";

interface ResumeUploadProps {
  onUploadSuccess: (file: UploadedFile) => void;
  onCancel: () => void;
}

const FILE_ICONS: Record<string, typeof FileText> = {
  pdf: FileText,
  docx: FileText,
  doc: FileText,
  txt: FileText,
  jpg: Image,
  png: Image,
};

export function ResumeUpload({ onUploadSuccess, onCancel }: ResumeUploadProps) {
  const { uploading, progress, error, upload, clearError } = useResumeUpload();
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);

  const handleFile = useCallback(
    async (file: File) => {
      setSelectedFile(file);
      const result = await upload(file);
      if (result) {
        onUploadSuccess(result);
      }
    },
    [upload, onUploadSuccess]
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      const file = e.dataTransfer.files[0];
      if (file) handleFile(file);
    },
    [handleFile]
  );

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
  };

  const Icon = selectedFile
    ? FILE_ICONS[selectedFile.name.split(".").pop()?.toLowerCase() || ""] || File
    : Upload;

  return (
    <div className="border rounded-xl p-4 bg-card space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm font-medium">
          <Icon className="h-4 w-4 text-primary" />
          <span>上传简历</span>
        </div>
        <button
          onClick={onCancel}
          className="rounded-md p-1 hover:bg-accent transition-colors"
        >
          <X className="h-4 w-4 text-muted-foreground" />
        </button>
      </div>

      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        className={`
          relative flex flex-col items-center justify-center rounded-lg border-2 border-dashed p-6 cursor-pointer
          transition-colors
          ${dragging ? "border-primary bg-primary/5" : "border-muted-foreground/20 hover:border-primary/50"}
          ${uploading ? "pointer-events-none opacity-60" : ""}
        `}
      >
        <input
          type="file"
          accept=".pdf,.docx,.doc,.txt,.jpg,.png"
          onChange={handleChange}
          className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
          disabled={uploading}
        />

        {uploading ? (
          <div className="flex flex-col items-center gap-2">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
            <p className="text-sm text-muted-foreground">上传中 {progress}%</p>
            {progress > 0 && (
              <div className="w-32 h-1 bg-muted rounded-full overflow-hidden">
                <div
                  className="h-full bg-primary transition-all duration-300"
                  style={{ width: `${progress}%` }}
                />
              </div>
            )}
          </div>
        ) : selectedFile ? (
          <div className="flex flex-col items-center gap-2">
            {(() => {
              const Icon = FILE_ICONS[selectedFile.name.split(".").pop()?.toLowerCase() || ""] || File;
              return <Icon className="h-8 w-8 text-primary" />;
            })()}
            <p className="text-sm font-medium truncate max-w-full">{selectedFile.name}</p>
            <p className="text-xs text-muted-foreground">
              {(selectedFile.size / 1024).toFixed(1)} KB
            </p>
          </div>
        ) : (
          <>
            <Upload className="h-8 w-8 text-muted-foreground mb-2" />
            <p className="text-sm text-muted-foreground">
              拖拽简历到这里，或<span className="text-primary">点击选择</span>
            </p>
            <p className="text-xs text-muted-foreground/60 mt-1">
              支持 PDF、Word、TXT、图片（ JPG/PNG）
            </p>
          </>
        )}
      </div>

      {error && (
        <p className="text-xs text-destructive">{error}</p>
      )}
    </div>
  );
}
