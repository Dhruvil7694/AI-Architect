import { useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { NavNode, navigationTree } from "./navigationTree";

export function useSidebarNavigation() {
  const router = useRouter();
  const [stack, setStack] = useState<NavNode[][]>([navigationTree]);
  const [titleStack, setTitleStack] = useState<string[]>(["Elevation Studio"]);

  const currentLevel = stack[stack.length - 1];
  const currentTitle = titleStack[titleStack.length - 1];

  const goForward = useCallback((node: NavNode) => {
    if (node.children && node.children.length > 0) {
      setStack((prev) => [...prev, node.children!]);
      setTitleStack((prev) => [...prev, node.title]);
    } else if (node.href) {
      router.push(node.href);
    }
  }, [router]);

  const goBack = useCallback(() => {
    if (stack.length > 1) {
      setStack((prev) => prev.slice(0, -1));
      setTitleStack((prev) => prev.slice(0, -1));
    }
  }, [stack.length]);

  return {
    currentLevel,
    currentTitle,
    canGoBack: stack.length > 1,
    goForward,
    goBack,
    breadcrumbs: titleStack.join(" / ")
  };
}
