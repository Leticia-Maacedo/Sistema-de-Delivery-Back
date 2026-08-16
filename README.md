# ⚙️ Sistema de Delivery — Back-end

## 📌 Sobre o projeto

O **Sistema de Delivery** é um projeto acadêmico desenvolvido para a disciplina de **Desenvolvimento de Sistemas de Informação**.

O sistema tem como referência o funcionamento de plataformas de delivery, como o **iFood**, utilizando seus conceitos e funcionalidades como base para o desenvolvimento de uma solução própria.

O Back-end será responsável pelo processamento das regras de negócio, gerenciamento dos dados e disponibilização das APIs utilizadas pelo Front-end.

> 🚧 **Status:** Em desenvolvimento

## 🎯 Objetivo

Desenvolver uma API para o Sistema de Delivery, aplicando conceitos de desenvolvimento de sistemas, banco de dados, APIs, autenticação e arquitetura de software.

## 🏗️ Arquitetura

O projeto seguirá a arquitetura **MVC (Model-View-Controller)**, conforme requisito da disciplina.

A aplicação será organizada de forma a separar as responsabilidades entre:

* **Model:** representação e manipulação dos dados;
* **View:** camada responsável pela apresentação/retorno das informações;
* **Controller:** responsável pelo processamento das requisições e regras de negócio.

## 🛠️ Tecnologias

As tecnologias previstas para o desenvolvimento do Back-end são:

* Python
* SQLite
* SQL
* JWT ou OAuth
* Postman

> A lista de tecnologias poderá ser atualizada conforme as decisões técnicas do grupo.

## 📋 Funcionalidades previstas

### 👤 Usuário

* CRUD de usuário
* Cadastro de usuário
* Autenticação
* Login
* Utilização de JWT ou OAuth
* Integração com serviços externos de autenticação
* Testes das APIs utilizando Postman

### 📍 Local

* CRUD de local
* Cadastro e gerenciamento de locais
* Integração com Google Maps API

### 🔄 API

O Back-end disponibilizará APIs para comunicação com o Front-end e processamento das funcionalidades do sistema.

> Novas funcionalidades serão adicionadas conforme a evolução das Sprints.

## 🗄️ Banco de dados

O projeto utilizará **SQLite** como banco de dados relacional.

A modelagem e estrutura do banco serão desenvolvidas conforme os requisitos e regras de negócio definidos para o sistema.

> **Observação:** a disciplina determina que não seja utilizado banco de dados NoSQL.

## 📁 Estrutura do projeto

A estrutura de diretórios será definida conforme a implementação do Back-end.

```text
Sistema-de-Delivery-Back/
├── app/
│   ├── models/
│   ├── controllers/
│   ├── ...
├── tests/
├── database/
├── ...
└── README.md
```

> A estrutura acima é apenas uma organização inicial e poderá ser alterada conforme a implementação do projeto.

## 🚀 Execução

As instruções para instalação, configuração do ambiente, banco de dados e execução da API serão adicionadas após a configuração inicial do projeto.

## 🧪 Testes

Os endpoints da API serão testados inicialmente utilizando o **Postman**, conforme o planejamento das Sprints.

## 👥 Equipe

* Leticia da Silva Macedo
* Anna Julia Higa Farincho
* Geovane Soares da Silva
* Richard Ferreira do Nascimento Santos

## 📚 Contexto acadêmico

Projeto desenvolvido para a disciplina de **Desenvolvimento de Sistemas de Informação — Sistemas de Informação**, utilizando metodologia baseada em **Scrum e Sprints**.

O desenvolvimento contempla implementação, documentação, testes, modelagem de banco de dados e integração entre os componentes do sistema.
