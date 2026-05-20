export function Checkout() {
  return (
    <main data-penflow-id="checkout">
      <span data-penflow-id="checkout.order-summary">Order summary</span>
      <span data-penflow-id="checkout.selected-payment-method">Selected payment method</span>
      <button data-penflow-id="checkout.pay-now" onClick={() => undefined}>Pay now</button>
      <span data-penflow-id="payNowLabel">Pay now</span>
    </main>
  );
}
