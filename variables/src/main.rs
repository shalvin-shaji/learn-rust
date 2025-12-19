fn main() {
    let mut x = 5;
    println!("The value of x is {x}");
    x = 6;
    println!("The value of x is now {x}");
    let tup: (i32, f32, char) = (45, 54.3, 'S');

    let (x, y, z) = tup;
    println!("The value of x is {x}");
    println!("The value of y is {y}");
    println!("The value of z is {z}");
}
