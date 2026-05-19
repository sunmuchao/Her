(() => {
  const createFallbackSvg = (label) => {
    const safeLabel = String(label || "Her").slice(0, 24);
    const svg = `
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 480 320" role="img" aria-label="${safeLabel}">
        <defs>
          <linearGradient id="bg" x1="0%" x2="100%" y1="0%" y2="100%">
            <stop offset="0%" stop-color="#f8fafc" />
            <stop offset="100%" stop-color="#e2e8f0" />
          </linearGradient>
          <linearGradient id="mark" x1="0%" x2="100%" y1="0%" y2="100%">
            <stop offset="0%" stop-color="#cbd5e1" />
            <stop offset="100%" stop-color="#94a3b8" />
          </linearGradient>
        </defs>
        <rect width="480" height="320" rx="28" fill="url(#bg)" />
        <circle cx="126" cy="116" r="42" fill="url(#mark)" opacity="0.68" />
        <path d="M56 250c24-58 68-88 132-88 56 0 102 26 142 78 18 24 42 38 78 44H56Z" fill="url(#mark)" opacity="0.54" />
        <text x="240" y="278" fill="#64748b" font-family="Avenir Next, PingFang SC, sans-serif" font-size="20" font-weight="600" text-anchor="middle">
          图片暂不可用
        </text>
      </svg>
    `;
    return `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`;
  };

  const applyFallback = (img) => {
    if (!img || img.dataset.fallback === "true") {
      return;
    }
    img.dataset.fallback = "true";
    img.src = createFallbackSvg(img.alt || "Her");
  };

  const enhanceImage = (img) => {
    if (!img) {
      return;
    }
    img.addEventListener(
      "error",
      () => {
        applyFallback(img);
      },
      { once: true },
    );
    if (!img.getAttribute("loading")) {
      img.setAttribute("loading", "lazy");
    }
    if ((img.getAttribute("src") || "").trim() === "") {
      applyFallback(img);
      return;
    }
    if (img.complete && !img.naturalWidth) {
      applyFallback(img);
    }
  };

  document.body.dataset.demoEnhanced = "true";
  document.querySelectorAll("img").forEach(enhanceImage);

  const observer = new MutationObserver((mutations) => {
    for (const mutation of mutations) {
      mutation.addedNodes.forEach((node) => {
        if (!(node instanceof HTMLElement)) {
          return;
        }
        if (node.tagName === "IMG") {
          enhanceImage(node);
          return;
        }
        node.querySelectorAll?.("img").forEach(enhanceImage);
      });
    }
  });

  observer.observe(document.body, { childList: true, subtree: true });
})();
