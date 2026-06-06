import type { MetadataRoute } from "next"

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: "*",
        allow: ["/", "/pricing", "/blog", "/blog/*"],
        disallow: ["/api/", "/dashboard/", "/onboarding/", "/settings/", "/legal/"],
      },
      {
        userAgent: "GPTBot",
        disallow: "/",
      },
    ],
    sitemap: "https://airecruit.com/sitemap.xml",
  }
}
