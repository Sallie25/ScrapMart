import { Button } from "@/components/ui/button";

export default function Home() {
  return (
    <main className="flex min-h-screen items-center justify-center gap-4">
      <Button variant="primary">
        Buy Scrap
      </Button>

      <Button variant="secondary">
        Contact Seller
      </Button>

      <Button variant="destructive">
        Delete Listing
      </Button>
    </main>
  );
}