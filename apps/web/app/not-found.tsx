import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4 p-6">
      <div className="text-6xl font-bold text-muted-foreground/40">404</div>
      <h2 className="text-lg font-semibold text-foreground">页面不存在</h2>
      <p className="text-sm text-muted-foreground max-w-md text-center">
        你访问的页面不存在或已被移动。
      </p>
      <Link href="/">
        <Button>回到首页</Button>
      </Link>
    </div>
  );
}
