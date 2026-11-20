/* global hexo */
'use strict';

/**
 * 没有文章时的归档页。
 *
 * **为什么需要它**：`hexo-generator-archive` 在一篇文章都没有的时候
 * 什么也不生成（`if (!allPosts.length) return;`）。于是站点上会少一个
 * `/archives/`——而导航里指着它。访客点「归档」得到 404，是那种
 * 「功能好像坏了」的 404，不是「这里还没有内容」的 404。
 *
 * **只补空的那一份**：有文章时归档页由 `hexo-generator-archive` 出
 * （它还管按年、按月分页），这里不插手。
 */
hexo.extend.generator.register('archives_fallback', function (locals) {
  if (locals.posts.length > 0) return [];

  return [
    {
      path: 'archives/index.html',
      layout: ['archive', 'index'],
      data: {
        archive: true,
        posts: locals.posts,
        total: 0,
      },
    },
  ];
});
