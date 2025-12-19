use rand::Rng;
use std::cmp::Ordering;
use std::io;

fn main() {
    let secret_number = rand::thread_rng().gen_range(1..=100);
    let mut tries = 0;
    println!("Guess the number!");
    loop {
        println!("Please input your guess.");
        let mut guess = String::new(); // Mutable string variable
        io::stdin()
            .read_line(&mut guess)
            .expect("Failed to read the guess.");
        tries += 1;

        let guess: u32 = match guess.trim().parse() {
            Ok(num) => num,
            Err(_) => {
                println!("Invalid guess, try again!");
                continue;
            }
        };

        println!("You guessed: {guess}");

        match guess.cmp(&secret_number) {
            Ordering::Less => println!("Too small!"),
            Ordering::Greater => println!("Too big!"),
            Ordering::Equal => {
                println!("You win!");
                break;
            }
        }
    }
    println!("You guessed the number in {tries} tries");
}
