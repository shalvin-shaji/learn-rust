fn another_function() {
    println!("Another function is called");
}
fn main() {
    another_function();
    println!("Hello, world!");
    yet_another_function();
    let k = plus_one(34);
    println!("The value of k is {k}");
}
fn yet_another_function() {
    let x = if true { 5 } else { 6 };
    println!("Yet another function is called");
    println!("The value of x in yet_another function is {x}");
}

fn plus_one(x: i32) -> i32 {
    x + 1 // Implicitly returning since the line is an expression not a statement since there is
    // no semicolon at the end.
}
