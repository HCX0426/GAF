/** real ly provides translation language */
export type RealLocale = 'zh-CN' | 'en-US' | 'ja-JP' | 'ko-KR';

/** user optional language, includes " follow system " */
export type SupportedLocale = RealLocale | 'system';

export type LocaleMessages = Record<RealLocale, Record<string, string>>;
