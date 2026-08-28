/**
 * Password strength evaluation utility using @zxcvbn-ts/core
 *
 * zxcvbn provides realistic password strength estimation by checking against:
 * - Common passwords dictionary
 * - Names, surnames from US census
 * - Popular words from Wikipedia and American TV shows
 * - Common patterns: dates, repeats, sequences, keyboard patterns
 *
 * Returns score 0-4 (weak to strong) with actionable feedback
 */
import { ZxcvbnFactory } from '@zxcvbn-ts/core';
import { dictionary, translations } from '@zxcvbn-ts/language-en';

// Configure zxcvbn with English dictionary and translations
const zxcvbn = new ZxcvbnFactory({
  dictionary,
  translations,
});

/** Password strength level labels */
export type PasswordStrengthLevel = 'very_weak' | 'weak' | 'fair' | 'strong' | 'very_strong';

/** Password strength evaluation result */
export interface PasswordStrengthResult {
  /** Score from 0 (very weak) to 4 (very strong) */
  score: number;
  /** Human-readable strength level */
  level: PasswordStrengthLevel;
  /**
   * Antd theme token name for UI color (TD-294 Phase 1).
   * Consumer resolves via `theme.useToken().token[colorToken]`.
   * One of: 'colorError' | 'colorWarning' | 'colorSuccess' | 'colorTextQuaternary'.
   */
  colorToken: string;
  /** Strength label in Chinese */
  label: string;
  /** Progress bar percentage (0-100) */
  percent: number;
  /** List of suggestions to improve password */
  suggestions: string[];
  /** Estimated time to crack */
  crackTime: string;
}

/** Strength level configuration (TD-294 Phase 1: hex → antd token name) */
const LEVEL_CONFIG: Record<number, { level: PasswordStrengthLevel; colorToken: string; label: string }> = {
  0: { level: 'very_weak', colorToken: 'colorError', label: '极弱' },
  1: { level: 'weak', colorToken: 'colorWarning', label: '弱' },
  2: { level: 'fair', colorToken: 'colorWarning', label: '一般' },
  3: { level: 'strong', colorToken: 'colorSuccess', label: '强' },
  4: { level: 'very_strong', colorToken: 'colorSuccess', label: '非常强' },
};

/** Crack time human-readable conversion */
function formatCrackTime(seconds: number): string {
  if (seconds < 1) return '立即破解';
  if (seconds < 60) return `${Math.round(seconds)}秒`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}分钟`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)}小时`;
  if (seconds < 31536000) return `${Math.round(seconds / 86400)}天`;
  if (seconds < 315360000) return `${Math.round(seconds / 31536000)}年`;
  return '数百年';
}

/**
 * Evaluate password strength using @zxcvbn-ts/core
 * @param password - The password to evaluate
 * @param userInputs - Optional list of user-related inputs (username, email, etc.) to check against
 */
export function evaluatePasswordStrength(password: string, userInputs: string[] = []): PasswordStrengthResult {
  if (!password) {
    return {
      score: 0,
      level: 'very_weak',
      colorToken: 'colorTextQuaternary',
      label: '未输入',
      percent: 0,
      suggestions: ['请输入密码'],
      crackTime: '立即破解',
    };
  }

  // Run zxcvbn evaluation
  const result = zxcvbn.check(password, userInputs);

  const config = LEVEL_CONFIG[result.score];
  const suggestions: string[] = [];

  // Collect feedback suggestions
  if (result.feedback.warning) {
    suggestions.push(result.feedback.warning);
  }
  suggestions.push(...result.feedback.suggestions);

  // Translate common zxcvbn feedback to Chinese
  const translatedSuggestions = suggestions.map((s) => {
    const feedbackMap: Record<string, string> = {
      // Warnings
      'Straight rows of keys on your keyboard are easy to guess.': '键盘上的直线按键很容易被猜到',
      'Short keyboard patterns are easy to guess.': '短键盘模式很容易被猜到',
      'Repeated characters like "aaa" are easy to guess.': '重复字符如"aaa"很容易被猜到',
      'Repeated character patterns like "abcabcabc" are easy to guess.': '重复字符模式如"abcabcabc"很容易被猜到',
      'Common character sequences like "abc" are easy to guess.': '常见字符序列如"abc"很容易被猜到',
      'Recent years are easy to guess.': '最近的年份很容易被猜到',
      'Dates are easy to guess.': '日期很容易被猜到',
      'This is a heavily used password.': '这是一个非常常见的密码',
      'This is a frequently used password.': '这是一个频繁使用的密码',
      'This is a commonly used password.': '这是一个常用的密码',
      'This is similar to a commonly used password.': '这与常用密码相似',
      'Single words are easy to guess.': '单个单词很容易被猜到',
      'Single names or surnames are easy to guess.': '单个姓名很容易被猜到',
      'Common names and surnames are easy to guess.': '常见姓名很容易被猜到',
      'There should not be any personal or page related data.': '不应包含任何个人或页面相关数据',
      'Your password was exposed by a data breach on the Internet.': '您的密码已在互联网数据泄露中暴露',
      // Suggestions
      "Avoid predictable letter substitutions like '@' for 'a'.": '避免可预测的字母替换，如用@代替a',
      'Avoid reversed spellings of common words.': '避免常见单词的反向拼写',
      'Capitalize some, but not all letters.': '只大写部分字母，而非全部',
      'Capitalize more than the first letter.': '大写不止第一个字母',
      'Avoid dates and years that are associated with you.': '避免使用与你相关的日期和年份',
      'Avoid recent years.': '避免使用最近的年份',
      'Avoid years that are associated with you.': '避免使用与你相关的年份',
      'Avoid common character sequences.': '避免使用常见字符序列',
      'Avoid repeated words and characters.': '避免重复的单词和字符',
      'Use longer keyboard patterns and change typing direction multiple times.':
        '使用更长的键盘模式并多次改变输入方向',
      'Add more words that are less common.': '添加更多不常见的字词',
      'Use multiple words, but avoid common phrases.': '使用多个单词，但避免常见短语',
      'You can create strong passwords without using symbols, numbers, or uppercase letters.':
        '无需使用符号、数字或大写字母也能创建强密码',
      'If you use this password elsewhere, you should change it.': '如果在其他地方使用了此密码，应该更改它',
    };
    return feedbackMap[s] || s;
  });

  return {
    score: result.score,
    level: config.level,
    colorToken: config.colorToken,
    label: config.label,
    percent: (result.score / 4) * 100,
    suggestions: translatedSuggestions,
    crackTime: formatCrackTime(result.crackTimes.offlineSlowHashingXPerSecond.seconds),
  };
}

/**
 * Check if password meets minimum requirements
 * @param password - The password to check
 * @param minLength - Minimum length (default: 6)
 */
export function isPasswordValid(password: string, minLength = 6): boolean {
  return password.length >= minLength;
}
