fn main() {
    println!("Hello, world!");
    let convert = convert_farenheit_to_celsius(98.6);
    println!("The value of 98.6 F in celsius is {convert}");
    let nth = nth_fibonocci(10);
    println!("The 10th fibonocci number is {nth}");
    let nth = nth_fibonocci_loop(10);
    println!("The 10th fibonocci number is {nth}");
}

fn nth_fibonocci(n: u32) -> u32 {
    if n == 1 {
        return 0;
    }
    if n == 2 {
        return 1;
    }
    nth_fibonocci(n - 1) + nth_fibonocci(n - 2)
}

fn nth_fibonocci_loop(n: u32) -> u32 {
    let mut a = 0;
    let mut b = 1;
    let mut temp;
    if n == 1 {
        return 0;
    }
    if n == 2 {
        return 1;
    }

    for _ in 2..n {
        temp = b;
        b = a + b;
        a = temp;
    }
    b
}

fn convert_farenheit_to_celsius(temp: f64) -> f64 {
    // temp is C = (temp - 32) * 5 / 9
    (temp - 32.0) * (5.0 / 9.0)
}
