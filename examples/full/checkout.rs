use dioxus::prelude::*;

#[component]
pub fn Checkout() -> Element {
    rsx! {
        main { "data-penflow-id": "checkout",
            span { "data-penflow-id": "checkout.order-summary", "Order summary" }
            span { "data-penflow-id": "checkout.selected-payment-method", "Selected payment method" }
            button { "data-penflow-id": "checkout.pay-now", "Pay now" }
            span { "data-penflow-id": "payNowLabel", "Pay now" }
        }
    }
}
