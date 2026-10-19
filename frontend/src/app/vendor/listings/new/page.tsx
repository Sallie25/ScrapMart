
"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import { SiteHeader } from "@/components/layout/site-header";
import { saveVendorDemoListing } from "@/lib/data/vendor-listings";
import { saveVendorDemoPhoto } from "@/lib/data/vendor-listing-photos";

const MAX_PHOTO_SIZE = 5 * 1024 * 1024;

export default function NewVendorListingPage() {
  const [submitted, setSubmitted] = useState(false);
  const [photoName, setPhotoName] = useState("");
  const [photoFile, setPhotoFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState("");
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    return () => {
      if (previewUrl) {
        URL.revokeObjectURL(previewUrl);
      }
    };
  }, [previewUrl]);

  function handlePhotoChange(file: File | undefined) {
    setErrorMessage("");

    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
    }

    setPreviewUrl(null);

    if (!file) {
      setPhotoFile(null);
      setPhotoName("");
      return;
    }

    if (!file.type.startsWith("image/")) {
      setPhotoFile(null);
      setPhotoName("");
      setErrorMessage("Please select a valid image file.");
      return;
    }

    if (file.size > MAX_PHOTO_SIZE) {
      setPhotoFile(null);
      setPhotoName("");
      setErrorMessage(
        "The image must be 5 MB or smaller. Please choose a smaller file.",
      );
      return;
    }

    setPhotoFile(file);
    setPhotoName(file.name);
    setPreviewUrl(URL.createObjectURL(file));
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrorMessage("");

    const form = event.currentTarget;
    const formData = new FormData(form);

    const vendorName = String(formData.get("vendorName") ?? "").trim();
    const title = String(formData.get("title") ?? "").trim();
    const category = String(formData.get("category") ?? "");
    const condition = String(formData.get("condition") ?? "");
    const description = String(formData.get("description") ?? "").trim();
    const price = Number(formData.get("price"));
    const unit = String(formData.get("unit") ?? "kg");
    const quantity = Number(formData.get("quantity"));
    const location = String(formData.get("location") ?? "").trim();

    if (vendorName.length < 2) {
      setErrorMessage("Please enter a shop or vendor name.");
      return;
    }

    if (!Number.isFinite(price) || price <= 0) {
      setErrorMessage("Please enter a valid price greater than zero.");
      return;
    }

    if (!Number.isFinite(quantity) || quantity <= 0) {
      setErrorMessage("Please enter a valid quantity greater than zero.");
      return;
    }

    const listingId = crypto.randomUUID();

    setIsSaving(true);

    try {
      if (photoFile) {
        await saveVendorDemoPhoto(listingId, photoFile);
      }

      saveVendorDemoListing({
        id: listingId,
        vendorName,
        title,
        category,
        condition,
        description,
        price,
        unit,
        quantity,
        location,
        photoName,
        createdAt: new Date().toISOString(),
      });

      setSubmitted(true);
    } catch {
      setErrorMessage(
        "We couldn't save the listing or its photo in this browser. Please try again, or choose a smaller image.",
      );
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <>
      <SiteHeader />

      <main className="mx-auto max-w-3xl px-4 py-10 sm:px-6">
        <Link
          href="/vendor/dashboard"
          className="text-sm font-medium text-primary hover:underline"
        >
          ← Back to dashboard
        </Link>

        <div className="mt-5">
          <p className="text-sm font-medium text-primary">VENDOR WORKSPACE</p>
          <h1 className="mt-2 text-3xl font-bold tracking-tight text-text">
            Create a scrap listing
          </h1>
          <p className="mt-2 leading-6 text-muted">
            Give buyers the information they need to understand your material
            and contact you.
          </p>
        </div>

        {submitted ? (
          <section
            aria-live="polite"
            className="mt-8 rounded-xl border border-border bg-surface p-6"
          >
            <div className="text-3xl" aria-hidden="true">
              ✓
            </div>
            <h2 className="mt-3 text-xl font-bold text-text">
              Demo listing saved
            </h2>
            <p className="mt-2 leading-6 text-muted">
              Your listing has been saved in this browser for demonstration.
              It has not been uploaded to the ScrapMart backend or published
              to the public marketplace.
            </p>
            <div className="mt-6 flex flex-wrap gap-3">
              <button
                type="button"
                onClick={() => {
                  setSubmitted(false);
                  setPhotoName("");
                  setPhotoFile(null);
                  setPreviewUrl(null);
                  setErrorMessage("");
                }}
                className="rounded-md bg-primary px-4 py-2 font-medium text-white transition-colors hover:bg-primary-hover"
              >
                Create another listing
              </button>
              <Link
                href="/vendor/dashboard"
                className="inline-flex items-center rounded-md border border-border px-4 py-2 font-medium text-text hover:bg-background"
              >
                View dashboard
              </Link>
            </div>
          </section>
        ) : (
          <form
            onSubmit={handleSubmit}
            className="mt-8 space-y-6 rounded-xl border border-border bg-surface p-5 sm:p-7"
          >
            <div>
              <label
                htmlFor="vendorName"
                className="mb-2 block text-sm font-semibold text-text"
              >
                Shop / vendor name *
              </label>
              <input
                id="vendorName"
                name="vendorName"
                required
                minLength={2}
                maxLength={100}
                placeholder="e.g. Lagos Metal Hub"
                className="w-full rounded-md border border-border bg-background px-3 py-3 text-text outline-none focus:ring-2 focus:ring-primary"
              />
              <p className="mt-1 text-xs text-muted">
                Enter the name buyers should see on this listing.
              </p>
            </div>

            <div>
              <label
                htmlFor="title"
                className="mb-2 block text-sm font-semibold text-text"
              >
                Listing title *
              </label>
              <input
                id="title"
                name="title"
                required
                minLength={3}
                maxLength={100}
                placeholder="e.g. Clean aluminium scrap"
                className="w-full rounded-md border border-border bg-background px-3 py-3 text-text outline-none focus:ring-2 focus:ring-primary"
              />
            </div>

            <div className="grid gap-5 sm:grid-cols-2">
              <div>
                <label
                  htmlFor="category"
                  className="mb-2 block text-sm font-semibold text-text"
                >
                  Category *
                </label>
                <select
                  id="category"
                  name="category"
                  required
                  defaultValue=""
                  className="w-full rounded-md border border-border bg-background px-3 py-3 text-text outline-none focus:ring-2 focus:ring-primary"
                >
                  <option value="" disabled>
                    Select a category
                  </option>
                  <option value="Metals">Metals</option>
                  <option value="Plastics">Plastics</option>
                  <option value="Paper">Paper and cardboard</option>
                  <option value="Electronics">Electronics</option>
                  <option value="Glass">Glass</option>
                  <option value="Other">Other</option>
                </select>
              </div>

              <div>
                <label
                  htmlFor="condition"
                  className="mb-2 block text-sm font-semibold text-text"
                >
                  Condition *
                </label>
                <select
                  id="condition"
                  name="condition"
                  required
                  defaultValue=""
                  className="w-full rounded-md border border-border bg-background px-3 py-3 text-text outline-none focus:ring-2 focus:ring-primary"
                >
                  <option value="" disabled>
                    Select condition
                  </option>
                  <option value="Good">Good</option>
                  <option value="Used">Used</option>
                  <option value="Mixed">Mixed</option>
                  <option value="Faulty">Faulty</option>
                </select>
              </div>
            </div>

            <div>
              <label
                htmlFor="description"
                className="mb-2 block text-sm font-semibold text-text"
              >
                Description *
              </label>
              <textarea
                id="description"
                name="description"
                required
                minLength={10}
                maxLength={2000}
                rows={4}
                placeholder="Describe the material, quality, and any important details."
                className="w-full rounded-md border border-border bg-background px-3 py-3 text-text outline-none focus:ring-2 focus:ring-primary"
              />
            </div>

            <div className="grid gap-5 sm:grid-cols-2">
              <div>
                <label
                  htmlFor="price"
                  className="mb-2 block text-sm font-semibold text-text"
                >
                  Price in naira (₦) *
                </label>
                <input
                  id="price"
                  name="price"
                  type="number"
                  required
                  min="0.01"
                  step="0.01"
                  placeholder="3200"
                  className="w-full rounded-md border border-border bg-background px-3 py-3 text-text outline-none focus:ring-2 focus:ring-primary"
                />
              </div>

              <div>
                <label
                  htmlFor="unit"
                  className="mb-2 block text-sm font-semibold text-text"
                >
                  Price unit *
                </label>
                <select
                  id="unit"
                  name="unit"
                  required
                  defaultValue="kg"
                  className="w-full rounded-md border border-border bg-background px-3 py-3 text-text outline-none focus:ring-2 focus:ring-primary"
                >
                  <option value="kg">Per kilogram (kg)</option>
                  <option value="tonne">Per tonne</option>
                  <option value="piece">Per piece</option>
                  <option value="bundle">Per bundle</option>
                </select>
              </div>
            </div>

            <div className="grid gap-5 sm:grid-cols-2">
              <div>
                <label
                  htmlFor="quantity"
                  className="mb-2 block text-sm font-semibold text-text"
                >
                  Available quantity *
                </label>
                <input
                  id="quantity"
                  name="quantity"
                  type="number"
                  required
                  min="0.01"
                  step="any"
                  placeholder="e.g. 250"
                  className="w-full rounded-md border border-border bg-background px-3 py-3 text-text outline-none focus:ring-2 focus:ring-primary"
                />
              </div>

              <div>
                <label
                  htmlFor="location"
                  className="mb-2 block text-sm font-semibold text-text"
                >
                  Shop location *
                </label>
                <input
                  id="location"
                  name="location"
                  required
                  minLength={2}
                  maxLength={150}
                  placeholder="e.g. Ikeja, Lagos"
                  className="w-full rounded-md border border-border bg-background px-3 py-3 text-text outline-none focus:ring-2 focus:ring-primary"
                />
              </div>
            </div>

            <div>
              <label
                htmlFor="photo"
                className="mb-2 block text-sm font-semibold text-text"
              >
                Material photo (optional)
              </label>
              <input
                id="photo"
                name="photo"
                type="file"
                accept="image/*"
                onChange={(event) =>
                  handlePhotoChange(event.currentTarget.files?.[0])
                }
                className="block w-full rounded-md border border-border bg-background px-3 py-3 text-sm text-text file:mr-4 file:rounded-md file:border-0 file:bg-primary file:px-3 file:py-2 file:font-medium file:text-white"
              />

              {previewUrl && (
                <div className="mt-4">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={previewUrl}
                    alt="Preview of the selected scrap material"
                    className="max-h-64 w-full rounded-lg border border-border object-contain"
                  />
                </div>
              )}

              <p className="mt-2 text-xs text-muted">
                {photoName
                  ? `Selected file: ${photoName}`
                  : "Choose an image up to 5 MB. The image is stored in this browser for the prototype."}
              </p>
            </div>

            {errorMessage && (
              <p
                role="alert"
                className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700"
              >
                {errorMessage}
              </p>
            )}

            <div className="rounded-lg border border-border bg-background p-4">
              <p className="text-sm font-semibold text-text">Payment policy</p>
              <p className="mt-1 text-sm leading-6 text-muted">
                ScrapMart&apos;s MVP uses pay-on-delivery. Do not request
                advance payment through this listing.
              </p>
            </div>

            <p className="text-xs leading-5 text-muted">
              * Required fields. Listings are saved only in this browser
              until backend integration is implemented.
            </p>

            <button
              type="submit"
              disabled={isSaving}
              className="inline-flex w-full items-center justify-center rounded-md bg-primary px-5 py-3 font-semibold text-white transition-colors hover:bg-primary-hover disabled:cursor-not-allowed disabled:opacity-60 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2"
            >
              {isSaving ? "Saving listing..." : "Save demo listing"}
            </button>
          </form>
        )}
      </main>
    </>
  );
}
