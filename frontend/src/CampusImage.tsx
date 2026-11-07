import { useState } from 'react';

function campusImageUrl(src?: string) {
  try {
    const url = new URL(src || '');
    return url.protocol === 'https:' && url.hostname === 'image.fduhole.com' && !url.port
      && !url.username && !url.password && /^\/i\/.+\.(?:jpe?g|png|gif|webp|avif)$/i.test(url.pathname)
      ? url.href : undefined;
  } catch { return undefined; }
}

export function CampusImage({ src, alt }: { src?: string; alt?: string }) {
  const [failedSrc, setFailedSrc] = useState<string>();
  const url = campusImageUrl(src);
  if (!url) return <span className="source-image-note">{alt ? `[图片：${alt}]` : '[图片]'}（暂不支持此图片地址）</span>;
  if (failedSrc === url) return <span className="source-image-note" role="status">{alt || '树洞配图'}加载失败，图片可能已失效，请稍后重新展开来源。</span>;
  return <span className="source-image"><img src={url} alt={alt || '树洞帖子配图'} loading="lazy" decoding="async" referrerPolicy="no-referrer" onError={() => setFailedSrc(url)} /></span>;
}
