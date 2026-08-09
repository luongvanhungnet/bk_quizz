import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkMath from "remark-math";
import { cn } from "./ui";

interface MathMarkdownProps {
  children: string | null | undefined;
  className?: string;
  inline?: boolean;
  normalizeLegacy?: boolean;
}

export function MathMarkdown({
  children,
  className,
  inline = false,
  normalizeLegacy = false,
}: MathMarkdownProps) {
  const value = normalizeLegacy ? normalizeLegacyMathText(children ?? "") : children ?? "";
  const Root = inline ? "span" : "div";
  return (
    <Root className={cn("math-markdown min-w-0", className)}>
      <ReactMarkdown
        skipHtml
        remarkPlugins={[remarkMath]}
        rehypePlugins={[[rehypeKatex, { trust: false, strict: "warn", throwOnError: false }]]}
        components={inline ? { p: ({ children: content }) => <span>{content}</span> } : undefined}
      >
        {value}
      </ReactMarkdown>
    </Root>
  );
}

export function normalizeLegacyMathText(value: string): string {
  const trimmed = value.trim();
  if (!trimmed || /\$|\\\(|\\\[/.test(trimmed)) return value;
  if (!hasBalancedBraces(trimmed)) return value;
  const hasLatexSyntax =
    /\\(?:int|sum|prod|frac|sqrt|lim|alpha|beta|gamma|theta|pi|mathbf)\b|[_^](?:\{[^{}]+\}|[A-Za-z0-9])/.test(
      trimmed,
    );
  if (!hasLatexSyntax) return value;
  const looksLikeWholeFormula = /[=<>±×÷]/.test(trimmed) || trimmed.split(/\s+/).length <= 3;
  return looksLikeWholeFormula ? `$${trimmed}$` : value;
}

function hasBalancedBraces(value: string): boolean {
  let depth = 0;
  for (const character of value) {
    if (character === "{") depth += 1;
    if (character === "}") depth -= 1;
    if (depth < 0) return false;
  }
  return depth === 0;
}
