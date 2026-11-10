import { useEffect, useRef, useState } from "react";
import { fmtInt } from "../format";

/** A number that briefly glows when its value changes — motion explains change. */
export function Num({ value, format = fmtInt, className = "" }: { value: number; format?: (n: number) => string; className?: string }) {
  const prev = useRef(value);
  const [flash, setFlash] = useState(0);
  useEffect(() => {
    if (prev.current !== value) {
      prev.current = value;
      setFlash((f) => f + 1);
    }
  }, [value]);
  return (
    <span key={flash} className={className + (flash ? " num-changed" : "")}>
      {format(value)}
    </span>
  );
}
