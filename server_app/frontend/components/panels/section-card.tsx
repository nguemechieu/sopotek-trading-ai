import { ReactNode } from "react";

type SectionCardProps = {
  eyebrow: string;
  title: string;
  children: ReactNode;
  rightSlot?: ReactNode;
  className?: string;
};

export function SectionCard({ eyebrow, title, children, rightSlot, className = "" }: SectionCardProps) {
  return (
    <section className={`panel rounded-[30px] px-5 py-5 md:px-6 md:py-6 ${className}`.trim()}>
      <div className="mb-6 flex flex-col gap-4 border-b border-white/8 pb-5 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="eyebrow">{eyebrow}</p>
          <h2 className="mt-2 max-w-4xl text-[1.7rem] font-semibold leading-tight tracking-[-0.03em] text-sand md:text-[1.95rem]">
            {title}
          </h2>
        </div>
        {rightSlot}
      </div>
      {children}
    </section>
  );
}
