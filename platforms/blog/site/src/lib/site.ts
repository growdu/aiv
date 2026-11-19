/**
 * 站点身份与结构。
 *
 * **框架层不许写死「我是谁」**。名字、简介、首页首屏、导航、页脚都在
 * `data/site.json` 里——那是使用者定义的地方；这个模块只负责读出来、
 * 补上默认值、并且把「功能关着就不出现」的项滤掉。
 *
 * 各模块自己的规则不在这里：学习流在 `data/learning-path.json`，
 * 活动数字在 `data/activity.json`。
 */
import siteData from '../../data/site.json';
import { enabled as learningEnabled } from './learning';

export interface NavItem {
  key: string;
  href: string;
  label: string;
  /** 依赖的功能名。功能关着，这一项就不出现。 */
  feature?: string;
}

export interface HomeAction {
  label: string;
  href: string;
  feature?: string;
}

export interface SiteConfig {
  version: number;
  name: string;
  tagline: string;
  description: string;
  home: {
    title: string;
    lead: string;
    sub: string;
    actions: HomeAction[];
  };
  nav: NavItem[];
  search: { href: string; label: string } | null;
  footer: { note: string };
}

const config = siteData as unknown as SiteConfig;

/** 各模块的开/关。关掉的模块：页面不生成，导航项与首页按钮自动消失。 */
const features: Record<string, boolean> = {
  learning_path: learningEnabled,
};

export const site = config;

/** 站点名。面包屑、页脚、`<title>` 都用它。 */
export const siteName = config.name;

/** 站点一句话介绍。页面没给描述时的兜底。 */
export const siteDescription = config.description;

/** 一个功能开着没有。没写的功能一律当作开着。 */
export function featureOn(name?: string): boolean {
  if (!name) return true;
  return features[name] !== false;
}

/** 导航项（功能关着的已经滤掉）。 */
export const navItems: NavItem[] = (config.nav ?? []).filter((item) => featureOn(item.feature));

/** 首页首屏的按钮（同样滤掉功能关着的）。 */
export const homeActions: HomeAction[] = (config.home?.actions ?? []).filter((a) =>
  featureOn(a.feature),
);

/** 顶栏右侧的检索入口。用户不想给就写 null。 */
export const search = config.search ?? null;

/** 页脚那一行说明。 */
export const footerNote = config.footer?.note ?? '';

/** 首页大标题。 */
export const homeTitle = config.home?.title || config.name;

/** 首页副标题。 */
export const homeLead = config.home?.lead ?? '';

/** 首页第二句副标题。 */
export const homeSub = config.home?.sub ?? '';

/**
 * 页面标题。
 *
 * 首页用站名本身当标题（不重复拼），别的页面拼成「标题 · 站名」。
 */
export function pageTitle(title: string): string {
  return title === config.name ? title : `${title} · ${config.name}`;
}
