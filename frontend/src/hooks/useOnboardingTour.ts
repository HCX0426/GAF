/**
 * Onboarding tour state management hook.
 *
 * Manages tour step progress, skip/complete marks and localStorage persistence.
 * Used by the OnboardingTour component and by Layout/App to trigger the tour after first login.
 */
import { useCallback, useEffect, useState } from 'react';

export interface TourStep {
  target: string;
  title: string;
  content: string;
  placement: 'top' | 'bottom' | 'left' | 'right';
}

export interface UseOnboardingTourReturn {
  steps: TourStep[];
  currentStep: number;
  isActive: boolean;
  isCompleted: boolean;
  start: () => void;
  next: () => void;
  prev: () => void;
  skip: () => void;
  complete: () => void;
  reset: () => void;
}

/** localStorage key for onboarding completion state */
const STORAGE_KEY = 'gaf_onboarding_completed';

/** Default onboarding steps for the GAF platform */
const DEFAULT_STEPS: TourStep[] = [
  {
    target: '.ant-layout-sider',
    title: '欢迎使用 GAF',
    content: '首先连接你的设备，左侧导航栏可以快速切换各功能模块',
    placement: 'right',
  },
  {
    target: "[href='/tasks']",
    title: '创建流程',
    content: '在任务工作室中拖拽节点，可视化创建自动化流程',
    placement: 'right',
  },
  {
    target: "[href='/ops/scheduler']",
    title: '无人值守',
    content: '配置定时任务，让系统自动执行你的流程，无需人工干预',
    placement: 'right',
  },
  {
    target: '.anticon-bell',
    title: '通知中心',
    content: '查看系统通知、执行报告和异常告警信息',
    placement: 'bottom',
  },
  {
    target: "[href='/system/settings']",
    title: '个性化配置',
    content: '调整系统设置、无人值守策略和各项偏好配置',
    placement: 'right',
  },
];

function readCompleted(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === 'true';
  } catch {
    return false;
  }
}

function writeCompleted(value: boolean): void {
  try {
    localStorage.setItem(STORAGE_KEY, value ? 'true' : 'false');
  } catch {
    // silent failure
  }
}

export function useOnboardingTour(steps: TourStep[] = DEFAULT_STEPS): UseOnboardingTourReturn {
  const [currentStep, setCurrentStep] = useState(0);
  const [isActive, setIsActive] = useState(false);
  const [isCompleted, setIsCompleted] = useState(() => readCompleted());

  /** Persist completion status whenever it changes */
  useEffect(() => {
    writeCompleted(isCompleted);
  }, [isCompleted]);

  const start = useCallback(() => {
    setCurrentStep(0);
    setIsActive(true);
  }, []);

  const next = useCallback(() => {
    setCurrentStep((prev) => {
      if (prev >= steps.length - 1) {
        setIsActive(false);
        setIsCompleted(true);
        return prev;
      }
      return prev + 1;
    });
  }, [steps.length]);

  const prev = useCallback(() => {
    setCurrentStep((prev) => Math.max(0, prev - 1));
  }, []);

  const skip = useCallback(() => {
    setIsActive(false);
    setIsCompleted(true);
  }, []);

  const complete = useCallback(() => {
    setIsActive(false);
    setIsCompleted(true);
  }, []);

  const reset = useCallback(() => {
    setCurrentStep(0);
    setIsCompleted(false);
    setIsActive(false);
  }, []);

  return {
    steps,
    currentStep,
    isActive,
    isCompleted,
    start,
    next,
    prev,
    skip,
    complete,
    reset,
  };
}

export default useOnboardingTour;
