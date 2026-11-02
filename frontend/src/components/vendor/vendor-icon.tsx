import { BuyerIcon } from "../buyer/buyer-icon";
import { AuthIcon } from "../auth/auth-icon";
export function VendorIcon({
  name,
  className = "size-5",
}: {
  name: string;
  className?: string;
}) {
  if (name === "upload")
    return <AuthIcon name="upload" className={className} />;
  if (name === "plus")
    return (
      <svg
        aria-hidden="true"
        className={className}
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M12 5v14M5 12h14" />
      </svg>
    );
  return <BuyerIcon name={name} className={className} />;
}
