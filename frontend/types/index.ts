export interface ProcessStep {
  id: string;
  icon: string;
  title: string;
  subtitle: string;
}

export interface ButtonProps {
  variant?: "primary" | "secondary";
  children: React.ReactNode;
  onClick?: () => void;
  className?: string;
}
