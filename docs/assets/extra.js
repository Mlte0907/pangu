// 盘古文档站 — 客户端脚本

// 复制代码时去掉 ``` 标记
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('pre code').forEach(block => {
    const btn = document.createElement('button');
    btn.className = 'md-clipboard md-icon';
    btn.title = '复制';
    btn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M19 21H8V7h11m0-2H8a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2m-3-4H4a2 2 0 0 0-2 2v14h2V3h12V1z"/></svg>';
    block.parentNode.appendChild(btn);
  });
});

// 键盘快捷键
document.addEventListener('keydown', e => {
  // `/` 聚焦搜索
  if (e.key === '/' && e.target.tagName !== 'INPUT' && e.target.tagName !== 'TEXTAREA') {
    e.preventDefault();
    const search = document.querySelector('[data-md-component="search-query"]');
    if (search) search.focus();
  }
});
