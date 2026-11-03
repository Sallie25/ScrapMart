// Presentation model using fields from the existing Buyer orders response.
// This component does not fetch orders or establish authentication.
export type BuyerOrder = {
  id: string;
  status: string;
  vendor_business_name: string;
  currency: "NGN";
  total_amount: string;
  created_at: string;
  payment_method: string;
  item: { title: string; quantity: string; quantity_unit: string };
};

export type BuyerOrdersState =
  | { status: "unavailable" }
  | { status: "loading" }
  | { status: "error" }
  // Reserved for a successful authenticated orders response, never fixtures
  // or a fallback for authentication, network or service failures.
  | { status: "success"; orders: readonly BuyerOrder[] };

function EmptyBuyerOrders() {
  return (
    <div className="mx-auto max-w-md py-8 text-center sm:py-12">
      <svg
        aria-hidden="true"
        viewBox="0 0 240 180"
        className="mx-auto mb-6 w-52 max-w-full sm:w-60"
        fill="none"
      >
        <circle cx="120" cy="86" r="74" fill="#e8f7ee" />
        <ellipse cx="126" cy="157" rx="68" ry="7" fill="#dfe6e1" />
        <path
          d="M61 43h17l17 81h78"
          stroke="#064829"
          strokeWidth="5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path
          d="m83 63 100 5-12 40H93"
          fill="white"
          stroke="#08783e"
          strokeWidth="4"
          strokeLinejoin="round"
        />
        <path
          d="M110 77v17m24-15v15m24-13-2 13"
          stroke="#dfe6e1"
          strokeWidth="4"
          strokeLinecap="round"
        />
        <circle cx="106" cy="140" r="9" fill="#064829" />
        <circle cx="164" cy="140" r="9" fill="#064829" />
        <path d="M153 41c1-15 11-23 25-23-1 14-10 24-25 23Z" fill="#74d99b" />
        <path
          d="m151 46 16-17"
          stroke="#08783e"
          strokeWidth="3"
          strokeLinecap="round"
        />
        <circle cx="54" cy="102" r="5" fill="#74d99b" />
        <circle cx="195" cy="47" r="3" fill="#08783e" />
      </svg>
      <h2 className="buyer-display text-2xl font-extrabold sm:text-3xl">
        No orders yet
      </h2>
      <p className="buyer-muted mt-3 text-sm leading-relaxed sm:text-base">
        Your first order starts something useful. When you place an order, its
        details and progress will appear here.
      </p>
    </div>
  );
}

export function BuyerOrders({ state }: { state: BuyerOrdersState }) {
  return (
    <section
      className="buyer-card mx-auto max-w-3xl p-6 sm:p-10"
      data-orders-state={state.status}
      aria-labelledby="buyer-orders-title"
    >
      <p className="buyer-eyebrow">Buyer workspace</p>
      <h1 id="buyer-orders-title" className="buyer-title mt-2">
        My Orders
      </h1>
      {state.status === "unavailable" && (
        <p className="buyer-muted mt-4 leading-relaxed">
          Orders are not connected yet. Your order history will be available
          once secure account integration is ready.
        </p>
      )}
      {state.status === "loading" && (
        <p role="status" className="buyer-muted mt-6 flex items-center gap-3">
          <span
            aria-hidden="true"
            className="size-5 rounded-full border-2 border-[#dfe6e1] border-t-[#08783e] animate-spin"
          />
          Loading your orders…
        </p>
      )}
      {state.status === "error" && (
        <p
          role="alert"
          className="mt-6 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm leading-relaxed text-amber-950"
        >
          We couldn’t load your orders. Please try again later. Your order
          history has not been confirmed.
        </p>
      )}
      {state.status === "success" &&
        (state.orders.length === 0 ? (
          <EmptyBuyerOrders />
        ) : (
          <ul className="mt-6 grid gap-4" aria-label="Your orders">
            {state.orders.map((order) => (
              <li
                key={order.id}
                className="rounded-2xl border border-[#dfe6e1] p-4 sm:p-5"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <h2 className="min-w-0 break-words font-extrabold">
                    {order.item.title}
                  </h2>
                  <span className="buyer-soft rounded-full px-3 py-1 text-xs font-bold capitalize text-[#064829]">
                    {order.status.replaceAll("_", " ")}
                  </span>
                </div>
                <p className="buyer-muted mt-2 break-words text-sm">
                  {order.vendor_business_name}
                </p>
                <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
                  <div>
                    <dt className="buyer-muted">Order reference</dt>
                    <dd className="mt-1 break-all font-semibold">{order.id}</dd>
                  </div>
                  <div>
                    <dt className="buyer-muted">Quantity</dt>
                    <dd className="mt-1 font-semibold">
                      {order.item.quantity} {order.item.quantity_unit}
                    </dd>
                  </div>
                  <div>
                    <dt className="buyer-muted">Total</dt>
                    <dd className="buyer-green mt-1 font-bold">
                      {new Intl.NumberFormat("en-NG", {
                        style: "currency",
                        currency: order.currency,
                      }).format(Number(order.total_amount))}
                    </dd>
                  </div>
                  <div>
                    <dt className="buyer-muted">Payment method</dt>
                    <dd className="mt-1 font-semibold capitalize">
                      {order.payment_method.replaceAll("_", " ")}
                    </dd>
                  </div>
                </dl>
                <p className="buyer-muted mt-4 text-xs">
                  Placed{" "}
                  <time dateTime={order.created_at}>
                    {new Intl.DateTimeFormat("en-NG", {
                      dateStyle: "medium",
                      timeZone: "UTC",
                    }).format(new Date(order.created_at))}
                  </time>
                </p>
              </li>
            ))}
          </ul>
        ))}
    </section>
  );
}
