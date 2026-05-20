use dioxus::prelude::*;

#[component]
pub fn Checkout() -> Element {
    rsx! {
        main { "data-penflow-id": "checkout",
            span { "data-penflow-id": "checkout.title", "Checkout" }
            button { "data-penflow-id": "checkout.pay", "Pay" }
        }
    }
}
