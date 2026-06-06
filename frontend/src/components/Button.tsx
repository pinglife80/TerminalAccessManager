import React from 'react';
import { RefreshCw, LucideIcon } from 'lucide-react';

// 按钮变体类型
type ButtonVariant = 'primary' | 'success' | 'danger' | 'warning' | 'secondary' | 'ghost';
type ButtonSize = 'sm' | 'md' | 'lg';

// 主按钮组件 - 用于主要操作
interface PrimaryButtonProps {
  icon?: LucideIcon;
  label: string;
  onClick?: () => void;
  variant?: ButtonVariant;
  size?: ButtonSize;
  disabled?: boolean;
  loading?: boolean;
  className?: string;
  type?: 'button' | 'submit' | 'reset';
}

export const PrimaryButton: React.FC<PrimaryButtonProps> = ({
  icon: Icon,
  label,
  onClick,
  variant = 'primary',
  size = 'md',
  disabled = false,
  loading = false,
  className = '',
  type = 'button',
}) => {
  const variantStyles: Record<ButtonVariant, string> = {
    primary: 'bg-blue-600 hover:bg-blue-700 text-white shadow-md hover:shadow-lg',
    success: 'bg-green-600 hover:bg-green-700 text-white shadow-md hover:shadow-lg',
    danger: 'bg-red-600 hover:bg-red-700 text-white shadow-md hover:shadow-lg',
    warning: 'bg-yellow-500 hover:bg-yellow-600 text-white shadow-md hover:shadow-lg',
    secondary: 'bg-gray-100 hover:bg-gray-200 text-gray-700',
    ghost: 'bg-transparent hover:bg-gray-100 text-gray-700',
  };

  const sizeStyles: Record<ButtonSize, string> = {
    sm: 'px-3 py-1.5 text-sm gap-1.5',
    md: 'px-4 py-2.5 text-sm gap-2',
    lg: 'px-6 py-3 text-base gap-2.5',
  };

  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled || loading}
      className={`
        flex items-center justify-center rounded-lg font-medium
        transition-all duration-200 ease-in-out
        hover:-translate-y-0.5 active:translate-y-0
        disabled:opacity-50 disabled:cursor-not-allowed disabled:transform-none
        ${variantStyles[variant]}
        ${sizeStyles[size]}
        ${className}
      `}
    >
      {loading ? (
        <RefreshCw className="h-4 w-4 animate-spin" />
      ) : Icon ? (
        <Icon className={size === 'sm' ? 'h-4 w-4' : size === 'lg' ? 'h-5 w-5' : 'h-4 w-4'} />
      ) : null}
      <span>{loading ? 'Processing...' : label}</span>
    </button>
  );
};

// 图标按钮组件 - 用于表格操作等
interface IconButtonProps {
  icon: LucideIcon;
  onClick?: () => void;
  variant?: ButtonVariant;
  size?: ButtonSize;
  disabled?: boolean;
  loading?: boolean;
  title?: string;
  className?: string;
  active?: boolean;
}

export const IconButton: React.FC<IconButtonProps> = ({
  icon: Icon,
  onClick,
  variant = 'ghost',
  size = 'md',
  disabled = false,
  loading = false,
  title,
  className = '',
  active = false,
}) => {
  const variantStyles: Record<ButtonVariant, string> = {
    primary: 'text-blue-600 hover:bg-blue-100 active:bg-blue-200',
    success: 'text-green-600 hover:bg-green-100 active:bg-green-200',
    danger: 'text-red-600 hover:bg-red-100 active:bg-red-200',
    warning: 'text-yellow-600 hover:bg-yellow-100 active:bg-yellow-200',
    secondary: 'text-gray-600 hover:bg-gray-100 active:bg-gray-200',
    ghost: 'text-gray-500 hover:bg-gray-50 active:bg-gray-100',
  };

  const activeStyles: Record<ButtonVariant, string> = {
    primary: 'bg-blue-100 text-blue-700',
    success: 'bg-green-100 text-green-700',
    danger: 'bg-red-100 text-red-700',
    warning: 'bg-yellow-100 text-yellow-700',
    secondary: 'bg-gray-100 text-gray-700',
    ghost: 'bg-gray-50 text-gray-600',
  };

  const sizeStyles: Record<ButtonSize, string> = {
    sm: 'p-1.5',
    md: 'p-2',
    lg: 'p-3',
  };

  const iconSizes: Record<ButtonSize, string> = {
    sm: 'h-3.5 w-3.5',
    md: 'h-4 w-4',
    lg: 'h-5 w-5',
  };

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled || loading}
      title={title}
      className={`
        inline-flex items-center justify-center rounded-lg
        transition-all duration-150 ease-in-out
        disabled:opacity-50 disabled:cursor-not-allowed
        ${active ? activeStyles[variant] : variantStyles[variant]}
        ${sizeStyles[size]}
        ${className}
      `}
    >
      {loading ? (
        <RefreshCw className={`${iconSizes[size]} animate-spin`} />
      ) : (
        <Icon className={iconSizes[size]} />
      )}
    </button>
  );
};

// 按钮组组件 - 用于多个按钮排列
interface ButtonGroupProps {
  children: React.ReactNode;
  className?: string;
}

export const ButtonGroup: React.FC<ButtonGroupProps> = ({ children, className = '' }) => {
  return (
    <div className={`inline-flex items-center gap-1 ${className}`}>
      {children}
    </div>
  );
};

// 导出所有组件
export default PrimaryButton;