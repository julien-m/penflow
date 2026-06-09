use dioxus::prelude::*;

#[component]
pub fn Checkout() -> Element {
    rsx! {
        main { "data-penflow-id": "checkout",
            span { "data-penflow-id": "checkout.order-summary", "Order summary" }
            span { "data-penflow-id": "checkout.selected-payment-method", "Selected payment method" }
            button { "data-penflow-id": "checkout.pay-now", "data-testid": "checkout-pay-now",
                span { "data-penflow-id": "payNowLabel", "Pay now" }
            }
        }
    }
}
